import 'package:flutter/foundation.dart';
import 'dart:io' show Platform;

/// Live API used by release builds on physical devices.
const kProductionApiBaseUrl = 'https://hayya.nexuserp.store';

/// Hosts that only work on emulator / same PC (not on a real phone).
bool isDevOnlyApiHost(String raw) {
  final uri = Uri.tryParse(normalizeApiBaseUrl(raw));
  if (uri == null) return false;
  final host = uri.host.toLowerCase();
  return host == '10.0.2.2' || host == '127.0.0.1' || host == 'localhost';
}

/// Normalizes user input and returns default when [raw] is empty.
String normalizeApiBaseUrl(String raw) {
  var s = raw.trim();
  if (s.isEmpty) return defaultApiBaseUrl();
  if (!s.startsWith('http://') && !s.startsWith('https://')) {
    // Public hostnames → https; LAN / emulator → http
    if (RegExp(r'^\d+\.\d+\.\d+\.\d').hasMatch(s) || s.startsWith('10.0.2.2')) {
      s = 'http://$s';
    } else if (s.contains('.')) {
      s = 'https://$s';
    } else {
      s = 'http://$s';
    }
  }
  while (s.endsWith('/')) {
    s = s.substring(0, s.length - 1);
  }
  // Paths in the app already start with `/api/v1/...`; drop a mistaken `/api/v1` suffix here
  // (avoids duplicates when users save `http://host:5052/api/v1`).
  final low = s.toLowerCase();
  if (low.endsWith('/api/v1')) {
    s = s.substring(0, s.length - '/api/v1'.length);
    while (s.endsWith('/')) {
      s = s.substring(0, s.length - 1);
    }
  } else if (low.endsWith('/api') && !low.endsWith('/api/v1')) {
    s = s.substring(0, s.length - '/api'.length);
    while (s.endsWith('/')) {
      s = s.substring(0, s.length - 1);
    }
  }
  return s;
}

/// Returns a user-facing error when [raw] is not a host:port base URL.
String? validateApiBaseUrlInput(String raw) {
  final trimmed = raw.trim();
  if (trimmed.isEmpty) return null;

  final s = normalizeApiBaseUrl(trimmed);
  final uri = Uri.tryParse(s);
  if (uri == null || (uri.scheme != 'http' && uri.scheme != 'https') || uri.host.isEmpty) {
    return 'Enter a valid URL like https://hayya.nexuserp.store';
  }

  // Common typo: http://192.168.1.335052 (colon missing before port)
  if (RegExp(r'://\d+\.\d+\.\d+\.\d+\d{2,5}(?:/|$)').hasMatch(s)) {
    return 'Missing colon before port. Example: http://192.168.1.33:5052';
  }

  final authority = s.substring(s.indexOf('://') + 3).split('/').first;
  final isLanIp = RegExp(r'^\d+\.\d+\.\d+\.\d').hasMatch(uri.host);
  if (isLanIp && !authority.contains(':')) {
    return 'LAN IP needs a port, e.g. http://192.168.1.33:5052';
  }

  final port = uri.port;
  if (port <= 0 || port > 65535) {
    return 'Port must be between 1 and 65535';
  }

  return null;
}

/// Compile-time / platform default (no SharedPreferences).
String defaultApiBaseUrl() {
  const configured = String.fromEnvironment('API_BASE_URL', defaultValue: '');
  if (configured.isNotEmpty) return configured;

  const apiHost = String.fromEnvironment('API_HOST', defaultValue: '');
  const apiPort = String.fromEnvironment('API_PORT', defaultValue: '5051');

  const useAdbReverse =
      bool.fromEnvironment('USE_ADB_REVERSE', defaultValue: false);
  if (!kIsWeb && Platform.isAndroid) {
    if (useAdbReverse) {
      return 'http://127.0.0.1:$apiPort';
    }
    if (apiHost.isNotEmpty) {
      return 'http://$apiHost:$apiPort';
    }
    // 10.0.2.2 is emulator-only; real phones need the public API in release builds.
    if (kDebugMode) {
      return 'http://10.0.2.2:$apiPort';
    }
    return kProductionApiBaseUrl;
  }
  if (kDebugMode) {
    return 'http://127.0.0.1:$apiPort';
  }
  return kProductionApiBaseUrl;
}
