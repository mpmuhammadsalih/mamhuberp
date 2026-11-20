import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

import '../../core/network/api_error_handler.dart';
import '../../services/sales_ai_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/numeric_text_field.dart';
import 'sales_ai_session_header.dart';
import 'sales_invoice_cart_screen.dart';
import 'sales_invoice_catalog_step.dart';
import 'sales_invoice_form_screen.dart';
import '../../core/theme/app_theme.dart';

/// Voice-first AI Sales Mode: talk → catalog match → cart → continue to invoice.
class SalesAiModeScreen extends StatefulWidget {
  const SalesAiModeScreen({super.key, this.header});

  /// From the setup page (billing / customer / warehouse).
  final SalesAiSessionHeader? header;

  @override
  State<SalesAiModeScreen> createState() => _SalesAiModeScreenState();
}

class _AiLang {
  const _AiLang({
    required this.code,
    required this.label,
    required this.sttLocales,
    required this.ttsLocales,
    required this.welcome,
    this.rtl = false,
  });

  final String code;
  final String label;
  final List<String> sttLocales;
  final List<String> ttsLocales;
  final String welcome;
  final bool rtl;
}

class _SalesAiModeScreenState extends State<SalesAiModeScreen> {
  static const _accent = Color(0xFF0D9488);
  static const _navy = Color(0xFF0F172A);

  static const _languages = <_AiLang>[
    _AiLang(
      code: 'en',
      label: 'English',
      sttLocales: ['en_US', 'en_GB', 'en_IN', 'en'],
      ttsLocales: ['en-US', 'en-GB', 'en-IN'],
      welcome:
          'Hi — I\'m your AI sales assistant. Tap the mic and tell me what you need, '
          'for example: “5 full-fat milk and 10 orange juices.”',
    ),
    _AiLang(
      code: 'ml',
      label: 'മലയാളം',
      sttLocales: ['ml_IN', 'ml-IN', 'ml'],
      ttsLocales: ['ml-IN', 'ml_IN'],
      welcome:
          'ഹായ് — ഞാൻ നിങ്ങളുടെ AI സെയിൽസ് അസിസ്റ്റന്റ് ആണ്. മൈക്ക് അമർത്തി ആവശ്യമുള്ള സാധനങ്ങൾ പറയൂ, '
          'ഉദാ: “5 ഫുൾ ഫാറ്റ് മിൽക്കും 10 ഓറഞ്ച് ജ്യൂസും.”',
    ),
    _AiLang(
      code: 'hi',
      label: 'हिन्दी',
      sttLocales: ['hi_IN', 'hi-IN', 'hi'],
      ttsLocales: ['hi-IN', 'hi_IN'],
      welcome:
          'नमस्ते — मैं आपका AI सेल्स असिस्टेंट हूँ। माइक दबाकर बताएं क्या चाहिए, '
          'जैसे: “5 फुल-फैट मिल्क और 10 ऑरेंज जूस।”',
    ),
    _AiLang(
      code: 'ar',
      label: 'العربية',
      sttLocales: ['ar_SA', 'ar_AE', 'ar_EG', 'ar', 'ar_SA_#u-nu-latn'],
      ttsLocales: ['ar-SA', 'ar-AE', 'ar-EG', 'ar'],
      welcome:
          'مرحبًا — أنا مساعد المبيعات الذكي. اضغط على الميكروفون وقل ما تحتاجه، '
          'مثل: «5 حليب كامل الدسم و10 عصير برتقال.»',
      rtl: true,
    ),
  ];

  final _textCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final _speech = stt.SpeechToText();
  final _tts = FlutterTts();

  final List<SalesAiChatMessage> _history = [];
  final List<_UiBubble> _bubbles = [];
  List<SalesAiCartLine> _cart = [];
  List<SalesAiProduct> _suggestions = [];
  double _cartTotal = 0;

  _AiLang _lang = _languages.first;
  String? _resolvedSttLocale;
  List<stt.LocaleName> _deviceLocales = const [];

  bool _ready = false;
  bool _listening = false;
  bool _busy = false;
  bool _ttsOn = true;
  bool _openaiOk = true;
  bool _conversationOpen = false;
  String _status = 'Ready';
  String _liveTranscript = '';
  String? _error;
  Object? _errorCause;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _bootstrap());
  }

  @override
  void dispose() {
    _textCtrl.dispose();
    _scrollCtrl.dispose();
    _speech.stop();
    _tts.stop();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    final ai = context.read<SalesAiService>();
    try {
      await _speech.initialize();
      _deviceLocales = await _speech.locales();
      await _applyLanguage(_lang, announce: false);
      final ok = await ai.isConfigured();
      if (!mounted) return;
      setState(() {
        _openaiOk = ok;
        _ready = true;
        if (!ok) {
          _error = 'OPENAI_API_KEY is not configured on the server.';
        } else {
          _bubbles.add(_UiBubble(role: 'assistant', text: _lang.welcome));
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _ready = true;
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
      });
    }
  }

  String? _pickSttLocale(_AiLang lang) {
    final available = {
      for (final l in _deviceLocales) l.localeId.toLowerCase().replaceAll('-', '_'): l.localeId,
    };
    for (final cand in lang.sttLocales) {
      final key = cand.toLowerCase().replaceAll('-', '_');
      final exact = available[key];
      if (exact != null) return exact;
      final prefix = key.split('_').first;
      for (final entry in available.entries) {
        if (entry.key == prefix || entry.key.startsWith('${prefix}_')) {
          return entry.value;
        }
      }
    }
    return lang.sttLocales.first;
  }

  Future<void> _applyLanguage(_AiLang lang, {bool announce = true}) async {
    await _tts.stop();
    await _speech.stop();
    final sttLocale = _pickSttLocale(lang);
    String? ttsOk;
    for (final cand in lang.ttsLocales) {
      try {
        final r = await _tts.setLanguage(cand);
        if (r == 1 || r == true) {
          ttsOk = cand;
          break;
        }
      } catch (_) {}
    }
    if (ttsOk == null) {
      try {
        await _tts.setLanguage(lang.ttsLocales.first);
      } catch (_) {}
    }
    await _tts.setSpeechRate(lang.code == 'ar' ? 0.45 : 0.48);
    if (!mounted) return;
    setState(() {
      _lang = lang;
      _resolvedSttLocale = sttLocale;
      _listening = false;
      _liveTranscript = '';
      _status = 'Ready';
      if (announce) {
        _bubbles.add(_UiBubble(role: 'assistant', text: lang.welcome));
      }
    });
    if (announce) _scrollToEnd();
  }

  Future<void> _speak(String text) async {
    if (!_ttsOn || text.trim().isEmpty) return;
    await _tts.stop();
    setState(() => _status = 'Speaking');
    await _tts.speak(text);
    if (mounted) setState(() => _status = 'Ready');
  }

  Future<void> _toggleListen() async {
    if (_busy) return;
    if (_listening) {
      await _speech.stop();
      setState(() {
        _listening = false;
        _status = 'Ready';
      });
      final said = _liveTranscript.trim();
      if (said.isNotEmpty) {
        await _send(said);
      }
      return;
    }

    final mic = await Permission.microphone.request();
    if (!mic.isGranted) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Microphone permission is required for voice sales.')),
      );
      return;
    }

    final available = await _speech.initialize(
      onError: (e) {
        if (mounted) {
          setState(() {
            _listening = false;
            _status = 'Ready';
            _error = e.errorMsg;
          });
        }
      },
      onStatus: (s) {
        if (s == 'notListening' && mounted && _listening) {
          setState(() => _listening = false);
        }
      },
    );
    if (!available) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Speech recognition is not available on this device.')),
      );
      return;
    }

    await _tts.stop();
    setState(() {
      _listening = true;
      _liveTranscript = '';
      _status = 'Listening';
      _error = null;
    });
    await _speech.listen(
      onResult: (r) {
        if (!mounted) return;
        setState(() => _liveTranscript = r.recognizedWords);
        if (r.finalResult && _listening) {
          _speech.stop();
          setState(() {
            _listening = false;
            _status = 'Understanding';
          });
          final said = r.recognizedWords.trim();
          if (said.isNotEmpty) _send(said);
        }
      },
      listenOptions: stt.SpeechListenOptions(
        listenMode: stt.ListenMode.confirmation,
        cancelOnError: true,
        partialResults: true,
        listenFor: const Duration(seconds: 45),
        pauseFor: const Duration(seconds: 3),
        localeId: _resolvedSttLocale ?? _lang.sttLocales.first,
      ),
    );
  }

  Future<void> _send(String text) async {
    final msg = text.trim();
    if (msg.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _status = 'Understanding';
      _error = null;
      _errorCause = null;
      _bubbles.add(_UiBubble(role: 'user', text: msg));
      _textCtrl.clear();
      _liveTranscript = '';
    });
    _scrollToEnd();

    try {
      final history = List<SalesAiChatMessage>.from(_history);
      final result = await context.read<SalesAiService>().chat(
            message: msg,
            history: history,
            cart: _cart,
            language: _lang.code,
            warehouseId: widget.header?.warehouseId ?? '',
            customerCode: widget.header?.customerCode ?? '',
          );
      if (!mounted) return;
      final reply = _currencyText(result.reply);
      final speak = _currencyText(result.speak);
      _history
        ..add(SalesAiChatMessage(role: 'user', content: msg))
        ..add(SalesAiChatMessage(role: 'assistant', content: reply));
      setState(() {
        _bubbles.add(_UiBubble(role: 'assistant', text: reply));
        _cart = result.cart;
        _cartTotal = result.cartTotal;
        if (result.suggestions.isNotEmpty) {
          _suggestions = result.suggestions;
          // Show matched products immediately after identification.
          _conversationOpen = false;
        }
        _status = _friendlyStatus(result.status);
        _busy = false;
      });
      _scrollToEnd();
      await _speak(speak);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _status = 'Ready';
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
      });
    }
  }

  String _friendlyStatus(List<String> notes) {
    if (notes.isEmpty) return 'Ready';
    for (var i = notes.length - 1; i >= 0; i--) {
      final n = notes[i];
      final m = RegExp(r'^found_(\d+)_products$').firstMatch(n);
      if (m != null) {
        final count = m.group(1);
        return count == '1' ? 'Found 1 product' : 'Found $count products';
      }
      if (n == 'search_products') return 'Searching products';
      if (n == 'get_product_details') return 'Identifying product';
      if (n == 'list_item_uoms') return 'Checking units';
      if (n == 'add_to_cart') return 'Adding to cart';
      if (n == 'reorder_last_sale' || n == 'reordered_last_sale') return 'Reordering last sale';
      if (n == 'get_alternatives') return 'Finding alternatives';
    }
    return notes.last.replaceAll('_', ' ');
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollCtrl.hasClients) return;
      _scrollCtrl.animateTo(
        _scrollCtrl.position.maxScrollExtent + 80,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  Future<void> _quickAdd(SalesAiProduct p, {String? unit, double? rate}) async {
    final picked = await _askQtyAndUnit(p, preferredUnit: unit, preferredRate: rate);
    if (picked == null || !mounted) return;
    final qty = picked.$1;
    final uom = picked.$2;
    final qtyLabel = qty == qty.roundToDouble() ? qty.round().toString() : qty.toStringAsFixed(2);
    await _send('Add $qtyLabel $uom of ${p.itemName} (item code ${p.itemCode}) to the cart.');
  }

  /// Returns (qty, unit) or null if cancelled.
  Future<(double, String)?> _askQtyAndUnit(
    SalesAiProduct p, {
    String? preferredUnit,
    double? preferredRate,
  }) async {
    final units = <SalesAiUomOption>[
      if (p.uoms.isNotEmpty)
        ...p.uoms
      else
        SalesAiUomOption(unit: p.unit, rate: p.rate, isBase: true),
    ];
    // Ensure default unit is present.
    if (!units.any((u) => u.unit.toUpperCase() == p.unit.toUpperCase())) {
      units.insert(0, SalesAiUomOption(unit: p.unit, rate: p.rate, isBase: true));
    }
    var selectedUnit = (preferredUnit ?? p.unit).trim().isEmpty ? p.unit : (preferredUnit ?? p.unit);
    if (!units.any((u) => u.unit.toUpperCase() == selectedUnit.toUpperCase())) {
      selectedUnit = units.first.unit;
    }
    final qtyCtrl = TextEditingController(text: '1');

    final result = await showModalBottomSheet<(double, String)>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setLocal) {
            final sel = units.firstWhere(
              (u) => u.unit.toUpperCase() == selectedUnit.toUpperCase(),
              orElse: () => units.first,
            );
            final rate = preferredRate != null &&
                    preferredUnit != null &&
                    preferredUnit.toUpperCase() == sel.unit.toUpperCase()
                ? preferredRate
                : (sel.rate > 0 ? sel.rate : p.rate);
            return Padding(
              padding: EdgeInsets.only(
                left: 16,
                right: 16,
                top: 4,
                bottom: MediaQuery.of(ctx).viewInsets.bottom + 16,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    p.itemName,
                    style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'SKU ${p.itemCode} · ${_money(rate)} / ${sel.unit}',
                    style: TextStyle(color: Colors.grey.shade700, fontSize: 13),
                  ),
                  const SizedBox(height: 14),
                  const Text('Quantity', style: TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  NumericTextField(
                    controller: qtyCtrl,
                    autofocus: true,
                    selectAllOnFocus: true,
                    labelText: 'Qty',
                    decoration: const InputDecoration(border: OutlineInputBorder()),
                  ),
                  if (units.length > 1) ...[
                    const SizedBox(height: 14),
                    const Text('Unit', style: TextStyle(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final u in units)
                          ChoiceChip(
                            label: Text(
                              u.rate > 0
                                  ? '${u.unit} · ${_money(u.rate)}'
                                  : u.unit,
                            ),
                            selected: u.unit.toUpperCase() == selectedUnit.toUpperCase(),
                            onSelected: (_) => setLocal(() => selectedUnit = u.unit),
                          ),
                      ],
                    ),
                  ],
                  const SizedBox(height: 16),
                  FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: _accent,
                      minimumSize: const Size.fromHeight(48),
                    ),
                    onPressed: () {
                      final qty = double.tryParse(qtyCtrl.text.trim().replaceAll(',', '')) ?? 0;
                      if (qty <= 0) return;
                      Navigator.of(ctx).pop((qty, selectedUnit));
                    },
                    child: const Text('Add to cart', style: TextStyle(fontWeight: FontWeight.w800)),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
    qtyCtrl.dispose();
    return result;
  }

  void _syncCartTotal() {
    _cartTotal = _cart.fold<double>(0, (s, l) => s + l.amount);
  }

  List<SalesInvoiceLineView> get _lineViews {
    return [
      for (var i = 0; i < _cart.length; i++)
        SalesInvoiceLineView(
          slno: i + 1,
          itemCode: _cart[i].itemCode,
          itemName: _cart[i].itemName,
          subtitle: [
            if (_cart[i].unit.isNotEmpty) _cart[i].unit,
            if (_cart[i].brand.isNotEmpty) _cart[i].brand,
          ].join(' · '),
          qty: _cart[i].qty,
          rate: _cart[i].rate,
          amount: _cart[i].amount,
          discount: _cart[i].discount,
        ),
    ];
  }

  Future<void> _openCart() async {
    if (_cart.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Cart is empty. Add products first.')),
      );
      return;
    }
    final proceedToCheckout = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (context) => SalesInvoiceCartScreen(
          getLines: () => _lineViews,
          getNetTotal: () => _cart.fold<double>(0, (s, l) => s + l.amount),
          onLineEdit: (_) async {
            if (!mounted) return;
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('UOM / bin / lot can be set on the sales invoice.'),
              ),
            );
          },
          onLineDelete: (index) {
            if (index < 0 || index >= _cart.length) return;
            setState(() {
              _cart = List<SalesAiCartLine>.from(_cart)..removeAt(index);
              _syncCartTotal();
            });
          },
          onQtyChanged: (index, qty) {
            if (index < 0 || index >= _cart.length) return;
            setState(() {
              final next = List<SalesAiCartLine>.from(_cart);
              next[index] = next[index].copyWith(qty: qty);
              _cart = next;
              _syncCartTotal();
            });
          },
          onRateChanged: (index, rate) {
            if (index < 0 || index >= _cart.length) return;
            setState(() {
              final next = List<SalesAiCartLine>.from(_cart);
              final line = next[index];
              final disc = line.discount > rate ? rate : line.discount;
              next[index] = line.copyWith(rate: rate, discount: disc);
              _cart = next;
              _syncCartTotal();
            });
          },
          onDiscountChanged: (index, discount) {
            if (index < 0 || index >= _cart.length) return;
            setState(() {
              final next = List<SalesAiCartLine>.from(_cart);
              final line = next[index];
              final disc = discount < 0 ? 0.0 : (discount > line.rate ? line.rate : discount);
              next[index] = line.copyWith(discount: disc);
              _cart = next;
              _syncCartTotal();
            });
          },
        ),
      ),
    );
    if (!mounted) return;
    setState(() {});
    if (proceedToCheckout == true) {
      await _openInvoice();
    }
  }

  Future<void> _openInvoice() async {
    if (_cart.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Cart is empty. Add products first.')),
      );
      return;
    }
    final seed = _cart.map((e) => e.toJson()).toList();
    final h = widget.header;
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => SalesInvoiceFormScreen(
          seedAiCart: seed,
          seedBillingType: h?.billingType,
          seedWalkIn: h?.walkIn,
          seedCustomer: h?.customer,
          seedWarehouse: h?.warehouse,
          seedAddress: h?.address,
          seedOrderNo: h?.orderNo,
          seedRemarks: h?.remarks,
        ),
      ),
    );
  }

  String _fmtNum(double v) => v.toStringAsFixed(2);
  String _money(double v) => 'QR ${_fmtNum(v)}';

  /// Prefer QR over $ / USD in AI chat and TTS.
  String _currencyText(String text) {
    var s = text;
    s = s.replaceAllMapped(RegExp(r'\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)'), (m) => 'QR ${m[1]}');
    s = s.replaceAllMapped(
      RegExp(r'\bUSD\s*([0-9][0-9,]*(?:\.[0-9]+)?)', caseSensitive: false),
      (m) => 'QR ${m[1]}',
    );
    s = s.replaceAllMapped(
      RegExp(r'\b([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:USD|dollars?|bucks)\b', caseSensitive: false),
      (m) => 'QR ${m[1]}',
    );
    return s;
  }

  void _openConversationDrawer() {
    setState(() => _conversationOpen = true);
    _scrollToEnd();
  }

  void _closeConversationDrawer() {
    if (!_conversationOpen) return;
    setState(() => _conversationOpen = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF1F5F9),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('AI Sales Mode', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
            if (widget.header != null)
              Text(
                [
                  widget.header!.walkIn
                      ? 'Walk-in'
                      : (widget.header!.customer?.name.isNotEmpty == true
                          ? widget.header!.customer!.name
                          : widget.header!.billingType),
                  if (widget.header!.warehouse != null &&
                      (widget.header!.warehouse!.label.isNotEmpty ||
                          widget.header!.warehouse!.warehouseName.isNotEmpty))
                    widget.header!.warehouse!.label.isNotEmpty
                        ? widget.header!.warehouse!.label
                        : widget.header!.warehouse!.warehouseName,
                ].join(' · '),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: Colors.grey.shade600),
              ),
          ],
        ),
        centerTitle: false,
        actions: [
          PopupMenuButton<_AiLang>(
            tooltip: 'Language',
            initialValue: _lang,
            onSelected: (lang) {
              if (lang.code == _lang.code || _busy || _listening) return;
              _applyLanguage(lang);
            },
            itemBuilder: (_) => [
              for (final lang in _languages)
                PopupMenuItem<_AiLang>(
                  value: lang,
                  child: Row(
                    children: [
                      if (lang.code == _lang.code)
                        const Icon(Icons.check, size: 18, color: _accent)
                      else
                        const SizedBox(width: 18),
                      const SizedBox(width: 8),
                      Text(lang.label),
                    ],
                  ),
                ),
            ],
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Row(
                children: [
                  const Icon(Icons.language_rounded, size: 20),
                  const SizedBox(width: 4),
                  Text(_lang.label, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
                ],
              ),
            ),
          ),
          IconButton(
            tooltip: _ttsOn ? 'Voice replies on' : 'Voice replies off',
            onPressed: () => setState(() => _ttsOn = !_ttsOn),
            icon: Icon(_ttsOn ? Icons.volume_up_rounded : Icons.volume_off_rounded),
          ),
          IconButton(
            tooltip: _conversationOpen ? 'Close conversation' : 'Conversation',
            onPressed: () {
              if (_conversationOpen) {
                _closeConversationDrawer();
              } else {
                _openConversationDrawer();
              }
            },
            icon: Badge(
              isLabelVisible: _bubbles.length > 1,
              label: Text('${_bubbles.length > 99 ? 99 : _bubbles.length}'),
              child: Icon(
                _conversationOpen ? Icons.chat_rounded : Icons.chat_bubble_outline_rounded,
              ),
            ),
          ),
        ],
      ),
      body: !_ready
          ? const Center(child: CircularProgressIndicator(color: _accent))
          : Column(
              children: [
                if (_error != null) ApiErrorBanner(message: _error!, error: _errorCause),
                _statusBar(),
                Expanded(
                  child: Stack(
                    children: [
                      Positioned.fill(child: _productsPane()),
                      if (_conversationOpen)
                        Positioned.fill(
                          child: Material(
                            elevation: 6,
                            color: Colors.white,
                            child: SafeArea(
                              top: false,
                              bottom: false,
                              child: _conversationDrawer(),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                _cartSummaryBar(),
                _composer(),
              ],
            ),
    );
  }

  Widget _statusBar() {
    return Material(
      color: Colors.white,
      child: InkWell(
        onTap: () {
          if (_conversationOpen) {
            _closeConversationDrawer();
          } else {
            _openConversationDrawer();
          }
        },
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          child: Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: _listening
                      ? Colors.redAccent
                      : _busy
                          ? Colors.orange
                          : _accent,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                _status,
                style: TextStyle(fontWeight: FontWeight.w700, color: Colors.grey.shade700, fontSize: 12.5),
              ),
              if (_liveTranscript.isNotEmpty) ...[
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    _liveTranscript,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(color: Colors.grey.shade600, fontSize: 12.5),
                  ),
                ),
              ] else
                const Spacer(),
              if (!_openaiOk)
                Text('AI offline', style: TextStyle(color: Colors.red.shade700, fontWeight: FontWeight.w700, fontSize: 12))
              else
                Icon(
                  _conversationOpen ? Icons.expand_more_rounded : Icons.chat_bubble_outline_rounded,
                  size: 18,
                  color: Colors.grey.shade500,
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _conversationDrawer() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 4, 8, 4),
          child: Row(
            children: [
              IconButton(
                tooltip: 'Close',
                onPressed: _closeConversationDrawer,
                icon: const Icon(Icons.close_rounded),
              ),
              const Expanded(
                child: Text(
                  'Conversation',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
                ),
              ),
              TextButton(
                onPressed: _closeConversationDrawer,
                child: const Text('Products'),
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: ListView.builder(
            controller: _scrollCtrl,
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 16),
            itemCount: _bubbles.length,
            itemBuilder: (_, i) {
              final b = _bubbles[i];
              final mine = b.role == 'user';
              return Align(
                alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
                child: Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  constraints: const BoxConstraints(maxWidth: 420),
                  decoration: BoxDecoration(
                    color: mine ? _accent.withValues(alpha: 0.12) : const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        mine ? 'You' : 'AI Sales',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w800,
                          color: mine ? _accent : _navy,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        b.text,
                        textDirection: _lang.rtl ? TextDirection.rtl : TextDirection.ltr,
                        style: const TextStyle(height: 1.35),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _productsPane() {
    final wide = MediaQuery.of(context).size.width >= 700;
    return Container(
      margin: const EdgeInsets.fromLTRB(10, 8, 10, 4),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 6),
            child: Row(
              children: [
                const Expanded(
                  child: Text('Matched products', style: TextStyle(fontWeight: FontWeight.w800)),
                ),
                Text(
                  _suggestions.isEmpty ? '' : '${_suggestions.length}',
                  style: TextStyle(fontWeight: FontWeight.w700, color: Colors.grey.shade600, fontSize: 12.5),
                ),
              ],
            ),
          ),
          Expanded(
            child: _suggestions.isEmpty
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Text(
                        'Speak or type what you need.\nProducts appear here as soon as they are identified.\nAI asks brand / unit / qty only when there are multiple options.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: Colors.grey.shade600, height: 1.4),
                      ),
                    ),
                  )
                : wide
                    ? GridView.builder(
                        padding: const EdgeInsets.fromLTRB(10, 0, 10, 10),
                        gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                          maxCrossAxisExtent: 340,
                          mainAxisExtent: 196,
                          crossAxisSpacing: 8,
                          mainAxisSpacing: 8,
                        ),
                        itemCount: _suggestions.length,
                        itemBuilder: (_, i) => _productCard(_suggestions[i]),
                      )
                    : ListView.separated(
                        padding: const EdgeInsets.fromLTRB(10, 0, 10, 10),
                        itemCount: _suggestions.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 8),
                        itemBuilder: (_, i) => _productCard(_suggestions[i]),
                      ),
          ),
        ],
      ),
    );
  }

  Widget _productCard(SalesAiProduct p) {
    final altUoms = p.uoms.where((u) => u.unit.toUpperCase() != p.unit.toUpperCase()).toList();
    return Material(
      color: const Color(0xFFF8FAFC),
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 8, 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              p.itemName,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14, height: 1.2),
            ),
            const SizedBox(height: 4),
            Text(
              [
                'SKU ${p.itemCode}',
                if (p.brand.isNotEmpty) p.brand,
                'Stock ${_fmtNum(p.stock)}',
              ].join(' · '),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 12, color: Colors.grey.shade600, height: 1.25),
            ),
            const SizedBox(height: 6),
            Text(
              '${_money(p.rate)} / ${p.unit}',
              style: const TextStyle(fontWeight: FontWeight.w800, color: _accent, fontSize: 15),
            ),
            if (altUoms.isNotEmpty) ...[
              const SizedBox(height: 6),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    for (final u in altUoms.take(4))
                      Padding(
                        padding: const EdgeInsets.only(right: 6),
                        child: ActionChip(
                          visualDensity: VisualDensity.compact,
                          label: Text(
                            u.rate > 0 ? '${u.unit} ${_money(u.rate)}' : u.unit,
                            style: const TextStyle(fontSize: 11.5),
                          ),
                          onPressed: _busy ? null : () => _quickAdd(p, unit: u.unit, rate: u.rate),
                        ),
                      ),
                  ],
                ),
              ),
            ],
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: _busy ? null : () => _quickAdd(p),
                child: const Text('Add'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _cartSummaryBar() {
    final count = _cart.length;
    final total = _money(_cartTotal);
    return Material(
      color: Colors.white,
      child: InkWell(
        onTap: count == 0 ? null : _openCart,
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
          decoration: const BoxDecoration(
            border: Border(top: BorderSide(color: Color(0xFFE2E8F0))),
          ),
          child: Row(
            children: [
              Icon(
                Icons.shopping_cart_outlined,
                size: 22,
                color: count == 0 ? Colors.grey.shade400 : const Color(0xFF1565C0),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  count == 0 ? 'Cart is empty' : 'Cart $count · Total $total',
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                    color: count == 0 ? Colors.grey.shade600 : const Color(0xFF111827),
                  ),
                ),
              ),
              if (count > 0)
                FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF1565C0),
                    minimumSize: const Size(0, 36),
                    padding: const EdgeInsets.symmetric(horizontal: 14),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                  onPressed: _openCart,
                  child: const Text('View cart', style: TextStyle(fontWeight: FontWeight.w700)),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _composer() {
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
        decoration: const BoxDecoration(
          color: Colors.white,
          border: Border(top: BorderSide(color: Color(0xFFE2E8F0))),
        ),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _textCtrl,
                enabled: !_busy && _openaiOk,
                minLines: 1,
                maxLines: 3,
                textInputAction: TextInputAction.send,
                textDirection: _lang.rtl ? TextDirection.rtl : TextDirection.ltr,
                onSubmitted: _send,
                decoration: InputDecoration(
                  hintText: _lang.code == 'ar'
                      ? 'اكتب أو تحدث عن طلبك…'
                      : _lang.code == 'hi'
                          ? 'ऑर्डर टाइप करें या बोलें…'
                          : _lang.code == 'ml'
                              ? 'ഓർഡർ ടൈപ്പ് ചെയ്യുക അല്ലെങ്കിൽ സംസാരിക്കുക…'
                              : 'Type or speak your order…',
                  isDense: true,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              style: IconButton.styleFrom(
                backgroundColor: _listening ? Colors.redAccent : _accent,
                foregroundColor: Colors.white,
                minimumSize: const Size(52, 52),
              ),
              onPressed: (!_openaiOk || _busy) ? null : _toggleListen,
              icon: Icon(_listening ? Icons.stop_rounded : Icons.mic_rounded),
            ),
            const SizedBox(width: 4),
            IconButton.filledTonal(
              onPressed: (!_openaiOk || _busy) ? null : () => _send(_textCtrl.text),
              icon: _busy
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.send_rounded),
            ),
          ],
        ),
      ),
    );
  }
}

class _UiBubble {
  const _UiBubble({required this.role, required this.text});
  final String role;
  final String text;
}
