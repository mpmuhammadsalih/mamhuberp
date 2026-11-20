import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/storage/login_credentials_storage.dart';
import '../providers/auth_provider.dart';
import '../widgets/nexus_erp_logo.dart';
import 'app_configuration_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _usernameCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  bool _rememberMe = true;
  bool _obscurePassword = true;
  static const _fontFamily = 'SF Pro Display';
  static const _titleStyle = TextStyle(
    fontFamily: _fontFamily,
    fontSize: 24,
    fontWeight: FontWeight.w800,
    letterSpacing: -0.2,
    color: Color(0xFF0D1B42),
    height: 1.15,
  );
  static const _subtitleStyle = TextStyle(
    fontFamily: _fontFamily,
    fontSize: 14,
    fontWeight: FontWeight.w400,
    color: Color(0xFF6F778A),
    height: 1.35,
  );
  static const _fieldHintStyle = TextStyle(
    fontFamily: _fontFamily,
    fontSize: 14,
    fontWeight: FontWeight.w400,
    color: Color(0xFF7D8597),
  );
  static const _smallLinkStyle = TextStyle(
    fontFamily: _fontFamily,
    fontSize: 13,
    fontWeight: FontWeight.w500,
    color: Color(0xFF2F66E8),
  );
  static const _rememberStyle = TextStyle(
    fontFamily: _fontFamily,
    fontSize: 13,
    fontWeight: FontWeight.w500,
    color: Color(0xFF5E6472),
  );
  static const _loginButtonStyle = TextStyle(
    fontFamily: _fontFamily,
    fontSize: 15,
    fontWeight: FontWeight.w600,
    letterSpacing: 0,
  );
  static const _actionButtonMinSize = Size(double.infinity, 48);
  static const _orStyle = TextStyle(
    fontFamily: _fontFamily,
    fontSize: 15,
    fontWeight: FontWeight.w500,
    color: Color(0xFF8B92A4),
  );
  static const _biometricStyle = TextStyle(
    fontFamily: _fontFamily,
    fontSize: 14.5,
    fontWeight: FontWeight.w600,
    color: Color(0xFF111E3D),
  );
  static const _footerStyle = TextStyle(
    fontFamily: _fontFamily,
    fontSize: 12,
    fontWeight: FontWeight.w400,
    color: Color(0xFF7B8293),
  );
  static const _versionStyle = TextStyle(
    fontFamily: _fontFamily,
    fontSize: 11.5,
    fontWeight: FontWeight.w400,
    color: Color(0xFFA2A9B8),
  );

  @override
  void initState() {
    super.initState();
    _loadSavedCredentials();
  }

  Future<void> _loadSavedCredentials() async {
    final saved = await LoginCredentialsStorage.read();
    if (!mounted) return;
    setState(() {
      _rememberMe = saved.rememberMe;
      if (saved.username.isNotEmpty) {
        _usernameCtrl.text = saved.username;
      }
      if (saved.rememberMe && saved.password.isNotEmpty) {
        _passwordCtrl.text = saved.password;
      }
    });
  }

  @override
  void dispose() {
    _usernameCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  Future<void> _openConfiguration() async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(builder: (_) => const AppConfigurationScreen()),
    );
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final auth = context.read<AuthProvider>();
    final username = _usernameCtrl.text.trim();
    final password = _passwordCtrl.text;
    final ok = await auth.login(username, password);
    if (ok && mounted) {
      await LoginCredentialsStorage.save(
        username: username,
        password: password,
        rememberMe: _rememberMe,
      );
      return;
    } else if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(auth.error ?? 'Login failed')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    return Scaffold(
      backgroundColor: const Color(0xFFF7F8FC),
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 430),
            child: SingleChildScrollView(
              keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
              padding: const EdgeInsets.all(10),
              child: Card(
                margin: EdgeInsets.zero,
                elevation: 0,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(36),
                  side: const BorderSide(color: Color(0xFFE9ECF3)),
                ),
                clipBehavior: Clip.antiAlias,
                child: Form(
                  key: _formKey,
                  child: Column(
                    children: [
                      const Padding(
                        padding: EdgeInsets.fromLTRB(22, 28, 22, 4),
                        child: NexusErpLogo(maxWidth: 220, maxHeight: 132),
                      ),
                      Padding(
                        padding: const EdgeInsets.fromLTRB(22, 8, 22, 20),
                        child: Column(
                          children: [
                            const Text(
                              'Sign in',
                              style: _titleStyle,
                            ),
                            const SizedBox(height: 8),
                            const Text(
                              'Use your credentials to continue',
                              textAlign: TextAlign.center,
                              style: _subtitleStyle,
                            ),
                            const SizedBox(height: 26),
                            TextFormField(
                              controller: _usernameCtrl,
                              decoration: const InputDecoration(
                                hintText: 'Username or employee code',
                                hintStyle: _fieldHintStyle,
                                prefixIcon: Icon(Icons.person_outline),
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.all(Radius.circular(14)),
                                ),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.all(Radius.circular(14)),
                                  borderSide: BorderSide(color: Color(0xFFE0E4EC)),
                                ),
                              ),
                              validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
                            ),
                            const SizedBox(height: 12),
                            TextFormField(
                              controller: _passwordCtrl,
                              obscureText: _obscurePassword,
                              decoration: InputDecoration(
                                hintText: 'Password',
                                hintStyle: _fieldHintStyle,
                                prefixIcon: const Icon(Icons.lock_outline),
                                suffixIcon: IconButton(
                                  onPressed: () {
                                    setState(() => _obscurePassword = !_obscurePassword);
                                  },
                                  icon: Icon(
                                    _obscurePassword ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                                  ),
                                ),
                                border: const OutlineInputBorder(
                                  borderRadius: BorderRadius.all(Radius.circular(14)),
                                ),
                                enabledBorder: const OutlineInputBorder(
                                  borderRadius: BorderRadius.all(Radius.circular(14)),
                                  borderSide: BorderSide(color: Color(0xFFE0E4EC)),
                                ),
                              ),
                              validator: (v) => (v == null || v.isEmpty) ? 'Required' : null,
                            ),
                            const SizedBox(height: 2),
                            Row(
                              children: [
                                Checkbox(
                                  value: _rememberMe,
                                  onChanged: (value) async {
                                    final next = value ?? false;
                                    setState(() => _rememberMe = next);
                                    if (!next) {
                                      _passwordCtrl.clear();
                                      await LoginCredentialsStorage.save(
                                        username: _usernameCtrl.text.trim(),
                                        password: '',
                                        rememberMe: false,
                                      );
                                    }
                                  },
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                                  visualDensity: VisualDensity.compact,
                                ),
                                const Text('Remember me', style: _rememberStyle),
                                const Spacer(),
                                TextButton(
                                  onPressed: () {
                                    ScaffoldMessenger.of(context).showSnackBar(
                                      const SnackBar(content: Text('Use ERP admin to reset password.')),
                                    );
                                  },
                                  child: const Text('Forgot Password?', style: _smallLinkStyle),
                                ),
                              ],
                            ),
                            SizedBox(
                              width: double.infinity,
                              child: FilledButton(
                                style: FilledButton.styleFrom(
                                  backgroundColor: const Color(0xFF2F66E8),
                                  elevation: 0,
                                  minimumSize: _actionButtonMinSize,
                                  padding: const EdgeInsets.symmetric(vertical: 14),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
                                ),
                                onPressed: auth.isLoading ? null : _submit,
                                child: auth.isLoading
                                    ? const SizedBox(
                                        width: 18,
                                        height: 18,
                                        child: CircularProgressIndicator(strokeWidth: 2),
                                      )
                                    : const Row(
                                        mainAxisAlignment: MainAxisAlignment.center,
                                        children: [
                                          Text(
                                            'Login',
                                            style: _loginButtonStyle,
                                          ),
                                          SizedBox(width: 10),
                                          Icon(Icons.arrow_forward_rounded, size: 20),
                                        ],
                                      ),
                              ),
                            ),
                            const SizedBox(height: 12),
                            SizedBox(
                              width: double.infinity,
                              child: OutlinedButton.icon(
                                style: OutlinedButton.styleFrom(
                                  minimumSize: _actionButtonMinSize,
                                  padding: const EdgeInsets.symmetric(vertical: 14),
                                  side: const BorderSide(color: Color(0xFF2F66E8)),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
                                ),
                                onPressed: auth.isLoading ? null : _openConfiguration,
                                icon: const Icon(Icons.settings_outlined, color: Color(0xFF2F66E8)),
                                label: const Text(
                                  'API server setup',
                                  style: TextStyle(
                                    fontFamily: _fontFamily,
                                    fontSize: 15,
                                    fontWeight: FontWeight.w600,
                                    color: Color(0xFF2F66E8),
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(height: 22),
                            const Row(
                              children: [
                                Expanded(child: Divider(color: Color(0xFFE0E4EC))),
                                Padding(
                                  padding: EdgeInsets.symmetric(horizontal: 12),
                                  child: Text(
                                    'OR',
                                    style: _orStyle,
                                  ),
                                ),
                                Expanded(child: Divider(color: Color(0xFFE0E4EC))),
                              ],
                            ),
                            const SizedBox(height: 16),
                            SizedBox(
                              width: double.infinity,
                              child: OutlinedButton.icon(
                                style: OutlinedButton.styleFrom(
                                  padding: const EdgeInsets.symmetric(vertical: 14),
                                  side: const BorderSide(color: Color(0xFFE0E4EC)),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
                                ),
                                onPressed: () {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(content: Text('Biometric login will be added next.')),
                                  );
                                },
                                icon: const Icon(Icons.fingerprint, color: Color(0xFF2F66E8)),
                                label: const Text('Login with Biometric', style: _biometricStyle),
                              ),
                            ),
                            const SizedBox(height: 18),
                            const Text('© 2024 Your Company. All rights reserved.', style: _footerStyle),
                            const SizedBox(height: 4),
                            const Text('V 1.0.0', style: _versionStyle),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

