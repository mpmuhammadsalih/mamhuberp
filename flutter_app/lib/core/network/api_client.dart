import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../storage/api_endpoint_storage.dart';
import '../storage/save_nonce_storage.dart';
import '../storage/token_storage.dart';
import 'api_base_url.dart';
import 'transaction_overlay_controller.dart';

/// Shared HTTP client for the mobile app.
///
/// Mutations (POST/PUT/PATCH/DELETE) automatically:
/// - send [X-Save-Nonce] via [SaveNonceStorage]
/// - show the global saving overlay via [TransactionOverlayController]
/// - rotate save_nonce from JSON responses
/// - run one authenticated mutation at a time (avoids nonce double-tap races)
///
/// See `flutter_app/DEVELOPMENT.md` and backend `mobile_backend/MUTATIONS.md`.
class ApiClient {
  ApiClient(this._tokenStorage, [this._transactionOverlay]);

  final TokenStorage _tokenStorage;
  final TransactionOverlayController? _transactionOverlay;

  static const _transactionOverlayExtraKey = 'transaction_overlay';
  static const _mutationDoneExtraKey = 'mutation_done';
  static const _saveNonceRetriedExtraKey = 'save_nonce_retried';

  /// Chains mutations so the next save waits for the prior nonce rotate.
  Future<void> _mutationMutex = Future<void>.value();

  static bool _isAuthPath(String path) {
    return path.contains('/api/v1/auth/login') ||
        path.contains('/api/v1/auth/refresh') ||
        path.contains('/api/v1/auth/logout');
  }

  static bool _isMutation(String method) {
    final m = method.toUpperCase();
    return m == 'POST' || m == 'PUT' || m == 'PATCH' || m == 'DELETE';
  }

  void _beginTransactionOverlay(RequestOptions options) {
    if (!_isMutation(options.method) || _isAuthPath(options.path)) return;
    if (options.extra[_transactionOverlayExtraKey] == true) return;
    options.extra[_transactionOverlayExtraKey] = true;
    _transactionOverlay?.begin();
  }

  void _endTransactionOverlay(RequestOptions options) {
    if (options.extra.remove(_transactionOverlayExtraKey) == true) {
      _transactionOverlay?.end();
    }
  }

  void _completeMutationGate(RequestOptions options) {
    final done = options.extra.remove(_mutationDoneExtraKey);
    if (done is Completer<void> && !done.isCompleted) {
      done.complete();
    }
  }

  /// Called when refresh fails and stored tokens are cleared (session no longer valid).
  void Function()? onSessionExpired;

  bool _handlingSessionExpiry = false;

  late final Dio dio = _buildDio();

  Dio _buildDio() {
    final client = Dio(
      BaseOptions(
        baseUrl: defaultApiBaseUrl(),
        connectTimeout: const Duration(seconds: 20),
        // ERP GRN / stock / accounts posts can exceed 20s.
        receiveTimeout: const Duration(seconds: 120),
        sendTimeout: const Duration(seconds: 60),
      ),
    );

    client.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          // Refresh must send the *refresh* token from Options; do not overwrite with access token.
          final path = options.path;
          final skipAccessBearer = path.contains('/api/v1/auth/refresh') ||
              path.contains('/api/v1/auth/login') ||
              path.contains('/api/v1/auth/logout');
          if (!skipAccessBearer) {
            final token = await _tokenStorage.getAccessToken();
            if (token != null && token.isNotEmpty) {
              options.headers['Authorization'] = 'Bearer $token';
            }
          }
          if (_isMutation(options.method) && !_isAuthPath(path)) {
            // 401/409 retries call fetch() with the same RequestOptions — keep the
            // existing mutex gate (do not await ourselves / deadlock).
            final alreadyGated = options.extra[_mutationDoneExtraKey] is Completer<void>;
            if (!alreadyGated) {
              final previous = _mutationMutex;
              final done = Completer<void>();
              _mutationMutex = done.future;
              options.extra[_mutationDoneExtraKey] = done;
              await previous;
            }
            final nonce = await SaveNonceStorage.read();
            if (nonce != null && nonce.isNotEmpty) {
              options.headers['X-Save-Nonce'] = nonce;
            }
            _beginTransactionOverlay(options);
          }
          handler.next(options);
        },
        onResponse: (response, handler) async {
          await SaveNonceStorage.applyFromResponseBody(response.data);
          _endTransactionOverlay(response.requestOptions);
          _completeMutationGate(response.requestOptions);
          handler.next(response);
        },
        onError: (err, handler) async {
          final req = err.requestOptions;
          final path = req.path;
          final isLogout401 =
              path.contains('/api/v1/auth/logout') && err.response?.statusCode == 401;

          final isAuthPath = path.contains('/api/v1/auth/refresh') ||
              path.contains('/api/v1/auth/login') ||
              path.contains('/api/v1/auth/logout');
          if (err.response?.statusCode == 401 && !isAuthPath) {
            final refreshed = await _refreshToken();
            if (refreshed != null) {
              // Same as save-nonce retry: release gate/overlay and clone options so
              // nested fetch cannot hang every authenticated mutation (SO/SI/GRN/…).
              _endTransactionOverlay(req);
              _completeMutationGate(req);
              final headers = Map<String, dynamic>.from(req.headers);
              headers['Authorization'] = 'Bearer $refreshed';
              final extra = Map<String, dynamic>.from(req.extra);
              extra.remove(_mutationDoneExtraKey);
              extra.remove(_transactionOverlayExtraKey);
              final opts = req.copyWith(headers: headers, extra: extra);
              try {
                final retry = await client.fetch(opts).timeout(
                  const Duration(seconds: 100),
                  onTimeout: () {
                    throw DioException(
                      requestOptions: opts,
                      type: DioExceptionType.receiveTimeout,
                      message: 'Request timed out after refreshing session. Try again.',
                    );
                  },
                );
                return handler.resolve(retry);
              } on DioException catch (retryErr) {
                _endTransactionOverlay(opts);
                _completeMutationGate(opts);
                return handler.next(retryErr);
              } catch (_) {
                _endTransactionOverlay(opts);
                _completeMutationGate(opts);
                return handler.next(err);
              }
            }
          }
          // Stale/used save nonce (e.g. after API restart or double-tap).
          // Rotate token and retry the mutation once with the fresh nonce.
          //
          // Important: release this attempt's overlay/mutex *before* nested fetch,
          // and clone RequestOptions so the retry re-enters the mutation gate.
          // Reusing the same options (Completer still open) can hang forever with
          // no error — Save stuck, invoice number unchanged.
          if (err.response?.statusCode == 409) {
            final body = err.response?.data;
            if (body is Map && body['replay_blocked'] == true) {
              await SaveNonceStorage.applyFromResponseBody(body);
              final alreadyRetried = req.extra[_saveNonceRetriedExtraKey] == true;
              if (!alreadyRetried && _isMutation(req.method) && !_isAuthPath(path)) {
                final nonce = await SaveNonceStorage.read();
                if (nonce != null && nonce.isNotEmpty) {
                  _endTransactionOverlay(req);
                  _completeMutationGate(req);

                  final headers = Map<String, dynamic>.from(req.headers);
                  headers['X-Save-Nonce'] = nonce;
                  final extra = Map<String, dynamic>.from(req.extra);
                  extra[_saveNonceRetriedExtraKey] = true;
                  extra.remove(_mutationDoneExtraKey);
                  extra.remove(_transactionOverlayExtraKey);

                  final opts = req.copyWith(headers: headers, extra: extra);
                  if (kDebugMode) {
                    debugPrint(
                      '[API] save-nonce 409 on ${req.method} ${req.path} — retrying once with fresh token',
                    );
                  }
                  try {
                    // Timeout so a Dio nested-fetch deadlock cannot leave Save silent.
                    final retry = await client.fetch(opts).timeout(
                      const Duration(seconds: 100),
                      onTimeout: () {
                        throw DioException(
                          requestOptions: opts,
                          type: DioExceptionType.receiveTimeout,
                          message:
                              'Save timed out after refreshing the save token. Tap Save once more.',
                        );
                      },
                    );
                    if (kDebugMode) {
                      debugPrint(
                        '[API] save-nonce retry OK ${req.method} ${req.path} → '
                        '${retry.statusCode}',
                      );
                    }
                    return handler.resolve(retry);
                  } on DioException catch (retryErr) {
                    if (kDebugMode) {
                      debugPrint(
                        '[API ERROR] save-nonce retry failed ${req.method} ${req.path} → '
                        '${retryErr.response?.statusCode ?? retryErr.type.name}',
                      );
                    }
                    _endTransactionOverlay(opts);
                    _completeMutationGate(opts);
                    return handler.next(retryErr);
                  } catch (e) {
                    if (kDebugMode) {
                      debugPrint(
                        '[API ERROR] save-nonce retry error ${req.method} ${req.path} → $e',
                      );
                    }
                    _endTransactionOverlay(opts);
                    _completeMutationGate(opts);
                    return handler.next(err);
                  }
                }
              }
            }
          }
          if (kDebugMode && !isLogout401) {
            debugPrint('[API ERROR] ${req.method} ${req.baseUrl}${req.path} → ${err.type.name} ${err.message}');
            final res = err.response;
            if (res != null) {
              debugPrint('[API ERROR] HTTP ${res.statusCode} ${res.data}');
            }
          }
          _endTransactionOverlay(req);
          _completeMutationGate(req);
          handler.next(err);
        },
      ),
    );
    return client;
  }

  /// Apply saved URL from preferences, or built-in default.
  Future<void> initializeEndpoint() async {
    final saved = await ApiEndpointStorage.readOverride();
    if (saved != null && saved.isNotEmpty) {
      if (kReleaseMode && isDevOnlyApiHost(saved)) {
        // Old installs often saved emulator URL; it cannot work on a real device.
        await ApiEndpointStorage.clearOverride();
        dio.options.baseUrl = defaultApiBaseUrl();
      } else {
        dio.options.baseUrl = normalizeApiBaseUrl(saved);
      }
    } else {
      dio.options.baseUrl = defaultApiBaseUrl();
    }
  }

  Future<void> setEndpointOverride(String rawInput) async {
    final url = normalizeApiBaseUrl(rawInput);
    await ApiEndpointStorage.saveOverride(url);
    dio.options.baseUrl = url;
  }

  Future<void> clearEndpointOverride() async {
    await ApiEndpointStorage.clearOverride();
    dio.options.baseUrl = defaultApiBaseUrl();
  }

  /// Quick reachability check (no auth). Returns null on success, else error text.
  Future<String?> probeHealthDetail(String rawBaseUrl) async {
    final base = normalizeApiBaseUrl(rawBaseUrl);
    try {
      final probe = Dio(
        BaseOptions(
          baseUrl: base,
          connectTimeout: const Duration(seconds: 12),
          receiveTimeout: const Duration(seconds: 12),
        ),
      );
      final response = await probe.get('/health');
      if (response.statusCode != 200) {
        return 'HTTP ${response.statusCode} from /health';
      }
      final data = response.data;
      if (data is Map && data['success'] == true) return null;
      return 'Unexpected /health response';
    } on DioException catch (e) {
      final detail = (e.message ?? e.error?.toString() ?? '').toLowerCase();
      if (detail.contains('certificate') ||
          detail.contains('handshake') ||
          detail.contains('ssl') ||
          detail.contains('tls')) {
        return 'SSL error — check device date/time or try http:// (same host)';
      }
      if (e.type == DioExceptionType.connectionError) {
        if (isDevOnlyApiHost(base)) {
          return '10.0.2.2 only works in the Android emulator. '
              'On a real phone use $kProductionApiBaseUrl';
        }
        return 'Connection failed — check URL, Wi‑Fi/mobile data, and that the server is up';
      }
      if (e.type == DioExceptionType.connectionTimeout) {
        return 'Timed out — server too slow or blocked';
      }
      final code = e.response?.statusCode;
      if (code != null) return 'HTTP $code from /health';
      return e.message ?? 'Network error';
    } catch (e) {
      return e.toString();
    }
  }

  Future<bool> probeHealth(String rawBaseUrl) async {
    final err = await probeHealthDetail(rawBaseUrl);
    return err == null;
  }

  Future<String?> _refreshToken() async {
    final refreshToken = await _tokenStorage.getRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) {
      _notifySessionExpired();
      return null;
    }
    try {
      final response = await dio.post(
        '/api/v1/auth/refresh',
        options: Options(headers: {'Authorization': 'Bearer $refreshToken'}),
      );
      final root = response.data;
      if (root is! Map<String, dynamic> || root['success'] != true) {
        throw DioException(
          requestOptions: response.requestOptions,
          response: response,
          type: DioExceptionType.badResponse,
        );
      }
      final data = root['data'];
      if (data is! Map<String, dynamic>) {
        throw DioException(
          requestOptions: response.requestOptions,
          response: response,
          type: DioExceptionType.badResponse,
        );
      }
      final access = data['access_token'];
      if (access is! String || access.isEmpty) {
        throw DioException(
          requestOptions: response.requestOptions,
          response: response,
          type: DioExceptionType.badResponse,
        );
      }
      final existingRefresh = await _tokenStorage.getRefreshToken() ?? refreshToken;
      await _tokenStorage.saveTokens(access, existingRefresh);
      await SaveNonceStorage.applyFromResponseBody(root);
      return access;
    } catch (_) {
      // Session clear (tokens/user/nav) happens in AuthProvider.clearLocalSession.
      _notifySessionExpired();
      return null;
    }
  }

  void _notifySessionExpired() {
    if (_handlingSessionExpiry) return;
    _handlingSessionExpiry = true;
    try {
      onSessionExpired?.call();
    } finally {
      _handlingSessionExpiry = false;
    }
  }
}
