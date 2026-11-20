import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/network/api_base_url.dart';
import '../core/network/api_client.dart';
import '../core/theme/app_theme.dart';

/// API base URL only (no database setup on device).
class AppConfigurationScreen extends StatefulWidget {
  const AppConfigurationScreen({super.key});

  @override
  State<AppConfigurationScreen> createState() => _AppConfigurationScreenState();
}

class _AppConfigurationScreenState extends State<AppConfigurationScreen> {
  final _apiUrlCtrl = TextEditingController();

  bool _probing = false;

  @override
  void initState() {
    super.initState();
    _apiUrlCtrl.addListener(() {
      if (mounted) setState(() {});
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadSaved());
  }

  @override
  void dispose() {
    _apiUrlCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadSaved() async {
    final api = context.read<ApiClient>();
    if (!mounted) return;
    setState(() {
      _apiUrlCtrl.text = api.dio.options.baseUrl;
    });
  }

  Future<void> _testApi() async {
    final urlError = validateApiBaseUrlInput(_apiUrlCtrl.text);
    if (urlError != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(urlError)));
      return;
    }
    setState(() => _probing = true);
    final api = context.read<ApiClient>();
    final err = await api.probeHealthDetail(_apiUrlCtrl.text);
    if (!mounted) return;
    setState(() => _probing = false);
    final normalized = normalizeApiBaseUrl(_apiUrlCtrl.text);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          err == null
              ? 'API reachable at $normalized'
              : 'Cannot reach API: $err',
        ),
      ),
    );
  }

  Future<void> _save() async {
    final raw = _apiUrlCtrl.text.trim();
    if (raw.isNotEmpty) {
      final urlError = validateApiBaseUrlInput(raw);
      if (urlError != null) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(urlError)));
        return;
      }
    }
    final api = context.read<ApiClient>();
    if (raw.isEmpty) {
      await api.clearEndpointOverride();
    } else {
      await api.setEndpointOverride(raw);
    }
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('API URL saved')),
    );
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: const Text('API server', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          const Text(
            'Set where the mobile app connects. Use the server root only — do not add /api/v1.',
            style: TextStyle(fontSize: 13, color: Color(0xFF6F778A), height: 1.35),
          ),
          const SizedBox(height: 8),
          Text(
            'Production: $kProductionApiBaseUrl\n'
            'Android emulator: http://10.0.2.2:5051\n'
            'LAN dev: http://192.168.x.x:5051',
            style: const TextStyle(fontSize: 12, color: Color(0xFF6F778A), height: 1.4),
          ),
          const SizedBox(height: 16),
          if (isDevOnlyApiHost(_apiUrlCtrl.text))
            Material(
              color: const Color(0xFFFFF3E0),
              borderRadius: BorderRadius.circular(12),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    const Icon(Icons.warning_amber_rounded, color: Color(0xFFE65100), size: 22),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'This address only works in the Android emulator. '
                        'On a real phone use $kProductionApiBaseUrl',
                        style: const TextStyle(fontSize: 12, color: Color(0xFF5D4037), height: 1.35),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          if (isDevOnlyApiHost(_apiUrlCtrl.text)) const SizedBox(height: 12),
          Material(
            color: Colors.white,
            borderRadius: BorderRadius.circular(14),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextField(
                    controller: _apiUrlCtrl,
                    decoration: InputDecoration(
                      labelText: 'Base URL',
                      hintText: kProductionApiBaseUrl,
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(),
                    ),
                    keyboardType: TextInputType.url,
                    autocorrect: false,
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton(
                    onPressed: _probing ? null : _testApi,
                    child: _probing
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Test API'),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _save,
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFF2F66E8),
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }
}
