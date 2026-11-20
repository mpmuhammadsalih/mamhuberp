import 'package:dio/dio.dart';

import 'api_base_url.dart';

const kAccessDeniedMessage =
    'You do not have access to this menu or feature. '
    'Contact your administrator to assign the correct role permissions in ERP.';

/// True when the API rejected the request due to missing role permission (HTTP 403).
bool isAccessDenied(Object e) {
  return e is DioException && e.response?.statusCode == 403;
}

String accessDeniedMessageFromStatus() => kAccessDeniedMessage;

/// User-facing access-denied text; prefers a clear server message over generic "Forbidden".
String accessDeniedMessage(Object e) {
  if (e is DioException) {
    final serverMsg = _messageFromBody(e.response?.data);
    if (serverMsg != null &&
        serverMsg.isNotEmpty &&
        !_isGenericForbidden(serverMsg) &&
        serverMsg.length < 600) {
      return serverMsg;
    }
  }
  return kAccessDeniedMessage;
}

bool _isGenericForbidden(String msg) {
  final lower = msg.trim().toLowerCase();
  return lower == 'forbidden' || lower == '403' || lower == '403 forbidden';
}

/// Best-effort user-facing message for API failures (handles FastAPI + dio).
String apiErrorMessage(Object e, {required bool authenticatedContext}) {
  if (e is! DioException) {
    var s = e.toString();
    if (s.startsWith('Exception: ')) s = s.substring(11);
    if (s.startsWith('Error: ')) s = s.substring(7);
    return s.length > 400 ? '${s.substring(0, 397)}…' : s;
  }

  final resp = e.response;
  final code = resp?.statusCode;
  final body = resp?.data;

  if (code == 403) {
    return accessDeniedMessage(e);
  }

  if (code == 409 && body is Map && body['replay_blocked'] == true) {
    return 'Save was interrupted (session token refreshed). Tap Save once more.';
  }

  final serverMsg = _messageFromBody(body);
  if (serverMsg != null &&
      serverMsg.isNotEmpty &&
      serverMsg.length < 600 &&
      !_isGenericForbidden(serverMsg)) {
    return serverMsg;
  }

  if (code == 401) {
    return authenticatedContext
        ? 'Session expired or login is no longer valid. Sign out and sign in again.'
        : 'Invalid username / employee code or password.';
  }
  if (code == 404) {
    final path = e.requestOptions.uri.path;
    final base = e.requestOptions.baseUrl;
    return 'Not found ($path). '
        'Use API base = server root only (e.g. http://IP:5051), not .../api/v1. '
        'If this is Business Summary, restart/deploy mobile API with the latest backend. Current base: $base';
  }
  if (code != null && code >= 500) {
    return 'Server error ($code). Check API logs and Oracle auth DB (login_users).';
  }
  if (body is String && body.isNotEmpty && body.length < 200) {
    return body;
  }
  if (e.type == DioExceptionType.badResponse && code != null) {
    return 'Request failed with HTTP $code.';
  }
  if (e.type == DioExceptionType.connectionTimeout ||
      e.type == DioExceptionType.sendTimeout ||
      e.type == DioExceptionType.receiveTimeout) {
    final path = e.requestOptions.uri.path;
    if (path.contains('business-summary')) {
      return 'Business Summary timed out. The server may still be querying ERP data — try again, '
          'or use a shorter date range. Also confirm mobile API is running (port 5051).';
    }
    if (path.contains('/reports/')) {
      return 'Report timed out. ERP may still be querying — try a shorter date range or narrower search, '
          'and confirm mobile API is running (port 5051).';
    }
    return 'Request timed out. Check that mobile API is running and reachable (e.g. http://10.0.2.2:5051 on emulator).';
  }
  if (e.type == DioExceptionType.connectionError) {
    final url = e.requestOptions.baseUrl;
    if (isDevOnlyApiHost(url)) {
      return 'Cannot reach the API at $url.\n\n'
          '10.0.2.2 only works in the Android emulator. '
          'Open API server setup and set:\n$kProductionApiBaseUrl';
    }
    return 'Cannot reach the API at:\n$url\n\n'
        'Quick fixes:\n'
        '• Production: open **API server setup** and set `$kProductionApiBaseUrl`\n'
        '• Local dev on a real phone: use your PC LAN IP (e.g. http://192.168.1.50:5051), '
        'same Wi‑Fi as the PC, API bound to 0.0.0.0\n'
        '• Start the API and allow inbound TCP on port 5051 in Windows Firewall';
  }
  final msg = e.message;
  if (msg != null && msg.isNotEmpty) return msg;
  return 'Request failed (${e.type.name}).';
}

String? _messageFromBody(Object? body) {
  if (body is Map) {
    final m = body['message'];
    if (m != null) return m.toString();

    final d = body['detail'];
    if (d is String) return d;
    if (d is List && d.isNotEmpty) {
      final item = d.first;
      if (item is Map && item['msg'] != null) return item['msg'].toString();
      return d.toString();
    }
    if (d != null) return d.toString();
  }
  return null;
}
