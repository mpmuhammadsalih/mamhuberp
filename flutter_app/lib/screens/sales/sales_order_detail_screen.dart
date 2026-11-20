import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/network/api_error_handler.dart';
import '../../widgets/api_error_banner.dart';
import '../../services/sales_service.dart';
import 'sales_invoice_detail_screen.dart';
import 'sales_order_form_screen.dart';
import '../../core/theme/app_theme.dart';

class SalesOrderDetailScreen extends StatefulWidget {
  const SalesOrderDetailScreen({super.key, required this.billno});

  final String billno;

  @override
  State<SalesOrderDetailScreen> createState() => _SalesOrderDetailScreenState();
}

class _SalesOrderDetailScreenState extends State<SalesOrderDetailScreen> {
  static const _accent = Color(0xFF1565C0);

  bool _loading = true;
  bool _converting = false;
  bool _cancelling = false;
  bool _pdfBusy = false;
  String? _error;
  Object? _errorCause;
  SalesInvoiceDetail? _detail;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final detail = await context.read<SalesService>().getOrderDetail(widget.billno);
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  Future<File> _writePdfFile() async {
    final bytes = await context.read<SalesService>().downloadOrderPdf(widget.billno);
    final dir = await getTemporaryDirectory();
    final safe = widget.billno.replaceAll(RegExp(r'[^\w\-]+'), '_');
    final file = File('${dir.path}/order_$safe.pdf');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<void> _sharePdf() async {
    if (_pdfBusy || widget.billno.trim().isEmpty) return;
    setState(() => _pdfBusy = true);
    try {
      final file = await _writePdfFile();
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'application/pdf')],
        subject: 'Sales Order ${widget.billno}',
        text: 'Sales Order ${widget.billno}',
      );
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  Future<void> _printCopy() async {
    if (_pdfBusy || widget.billno.trim().isEmpty) return;
    setState(() => _pdfBusy = true);
    try {
      final file = await _writePdfFile();
      final opened = await OpenFilex.open(file.path, type: 'application/pdf');
      if (!mounted) return;
      if (opened.type != ResultType.done) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(opened.message.isNotEmpty ? opened.message : 'Could not open PDF.')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  Future<void> _editOrder() async {
    final detail = _detail;
    if (detail == null || !detail.isPendingOrder) return;
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => SalesOrderFormScreen(editBillno: widget.billno),
      ),
    );
    if (saved == true && mounted) await _load();
  }

  Future<void> _cancelOrder() async {
    final detail = _detail;
    if (detail == null || _cancelling || !detail.isPendingOrder) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel sales order'),
        content: Text(
          'Cancel Order-${widget.billno}?\n\n'
          'This cannot be undone. The order will move to the Canceled tab.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Keep')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFC62828)),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Cancel order'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _cancelling = true);
    try {
      await context.read<SalesService>().cancelOrder(widget.billno);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Order-${widget.billno} cancelled.')),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _cancelling = false);
      final msg = handleApiError(context, e, authenticatedContext: true);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    }
  }

  Future<void> _convertToSale() async {
    final detail = _detail;
    if (detail == null || _converting) return;
    if (!detail.isPendingOrder) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            detail.isInvoicedOrder
                ? 'This order is already converted to a sale.'
                : 'This order cannot be converted.',
          ),
        ),
      );
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Convert to sale'),
        content: Text(
          'Create a sales invoice from Order-${widget.billno}?\n\n'
          'Customer: ${detail.summary.customerLabel}\n'
          'Net: ${detail.summary.netAmount.toStringAsFixed(2)}\n\n'
          'Cash orders are paid in full as cash. Credit orders post to the customer account.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Convert'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _converting = true);
    try {
      final result = await context.read<SalesService>().convertOrderToInvoice(widget.billno);
      if (!mounted) return;
      setState(() => _converting = false);
      await _load();
      if (!mounted) return;

      final openInvoice = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(result.alreadyInvoiced ? 'Already converted' : 'Converted to sale'),
          content: Text(
            result.message.isNotEmpty
                ? result.message
                : 'Invoice ${result.invoiceBillno} created from this order.',
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Close')),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('View invoice'),
            ),
          ],
        ),
      );

      if (!mounted) return;
      if (openInvoice == true && result.invoiceBillno.isNotEmpty) {
        await Navigator.of(context).push<void>(
          MaterialPageRoute<void>(
            builder: (_) => SalesInvoiceDetailScreen(billno: result.invoiceBillno),
          ),
        );
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _converting = false);
      final msg = handleApiError(context, e, authenticatedContext: true);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    }
  }

  String _fmtQty(double q) {
    if (q == q.roundToDouble()) return q.round().toString();
    return q.toStringAsFixed(2);
  }

  String _statusLabel(SalesInvoiceDetail detail) {
    if (detail.isInvoicedOrder) return 'INVOICED';
    if (detail.isCancelledOrder) return 'CANCELLED';
    return 'OPEN';
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    final busy = _loading || _converting || _cancelling || _pdfBusy;
    final canConvert = detail != null && detail.isPendingOrder && !busy;

    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text('Order-${widget.billno}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          if (detail != null)
            IconButton(
              tooltip: 'Share PDF',
              onPressed: busy ? null : _sharePdf,
              icon: _pdfBusy
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.share_outlined),
            ),
          if (detail != null)
            IconButton(
              tooltip: 'Print copy',
              onPressed: busy ? null : _printCopy,
              icon: const Icon(Icons.picture_as_pdf_outlined),
            ),
          if (detail != null && detail.isPendingOrder)
            IconButton(
              tooltip: 'Edit',
              onPressed: busy ? null : _editOrder,
              icon: const Icon(Icons.edit_outlined),
            ),
          if (detail != null && detail.isPendingOrder)
            IconButton(
              tooltip: 'Cancel order',
              onPressed: busy ? null : _cancelOrder,
              icon: const Icon(Icons.cancel_outlined, color: Color(0xFFC62828)),
            ),
          IconButton(onPressed: busy ? null : _load, icon: const Icon(Icons.refresh_rounded)),
        ],
      ),
      bottomNavigationBar: detail == null || !detail.isPendingOrder
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 8, 14, 12),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: busy ? null : _editOrder,
                            style: OutlinedButton.styleFrom(
                              foregroundColor: _accent,
                              minimumSize: const Size.fromHeight(46),
                              side: const BorderSide(color: _accent),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                            ),
                            icon: const Icon(Icons.edit_outlined),
                            label: const Text('Edit'),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          flex: 2,
                          child: FilledButton.icon(
                            onPressed: canConvert ? _convertToSale : null,
                            style: FilledButton.styleFrom(
                              backgroundColor: _accent,
                              minimumSize: const Size.fromHeight(46),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                            ),
                            icon: _converting
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                  )
                                : const Icon(Icons.point_of_sale_rounded),
                            label: Text(_converting ? 'Converting…' : 'Convert to sale'),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: busy ? null : _cancelOrder,
                        style: OutlinedButton.styleFrom(
                          foregroundColor: const Color(0xFFC62828),
                          minimumSize: const Size.fromHeight(44),
                          side: const BorderSide(color: Color(0xFFC62828)),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                        icon: _cancelling
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFFC62828)),
                              )
                            : const Icon(Icons.cancel_outlined),
                        label: Text(_cancelling ? 'Cancelling…' : 'Cancel order'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _accent))
          : _error != null
              ? ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _load)
              : detail == null
                  ? const Center(child: Text('Order not found.'))
                  : RefreshIndicator(
                      color: _accent,
                      onRefresh: _load,
                      child: ListView(
                        padding: const EdgeInsets.fromLTRB(14, 8, 14, 24),
                        children: [
                          _headerCard(detail.summary, detail.lines.length, detail),
                          const SizedBox(height: 12),
                          Text(
                            'Items (${detail.lines.length})',
                            style: TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                              color: Colors.grey.shade800,
                            ),
                          ),
                          const SizedBox(height: 8),
                          if (detail.lines.isEmpty)
                            Container(
                              padding: const EdgeInsets.all(20),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Text(
                                'No line items on this order.',
                                style: TextStyle(color: Colors.grey.shade600),
                              ),
                            )
                          else
                            ...detail.lines.map(_lineCard),
                        ],
                      ),
                    ),
    );
  }

  Widget _headerCard(SalesInvoiceSummary inv, int lineCount, SalesInvoiceDetail detail) {
    final isCredit = inv.billingType == 'CREDIT';
    final status = _statusLabel(detail);
    final statusColor = detail.isInvoicedOrder
        ? const Color(0xFF1565C0)
        : detail.isCancelledOrder
            ? const Color(0xFFC62828)
            : const Color(0xFF1C9C58);

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: isCredit ? const Color(0xFF8E24AA) : const Color(0xFF1BBF6B), width: 3)),
        boxShadow: const [BoxShadow(color: Color(0x12000000), blurRadius: 8, offset: Offset(0, 2))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  inv.customerLabel,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  status,
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: statusColor),
                ),
              ),
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: isCredit ? const Color(0xFFF3E5F5) : const Color(0xFFE9F9EF),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  inv.billingType,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: isCredit ? const Color(0xFF6A1B9A) : const Color(0xFF1C9C58),
                  ),
                ),
              ),
            ],
          ),
          if (inv.customerCode.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text('Code ${inv.customerCode}', style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
          ],
          if (inv.orderNo.isNotEmpty) ...[
            const SizedBox(height: 2),
            Text('Order ${inv.orderNo}', style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
          ],
          const SizedBox(height: 10),
          Row(
            children: [
              _metaChip(Icons.calendar_today_outlined, inv.billDate),
              const SizedBox(width: 8),
              _metaChip(Icons.format_list_numbered_rounded, '$lineCount lines'),
            ],
          ),
          const Divider(height: 22),
          Row(
            children: [
              const Text('Net total', style: TextStyle(fontSize: 13, color: Color(0xFF6F7482))),
              const Spacer(),
              Text(
                inv.netAmount.toStringAsFixed(2),
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 20, color: Color(0xFF3E63F5)),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _metaChip(IconData icon, String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: const Color(0xFFF0F4FA),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: _accent),
          const SizedBox(width: 4),
          Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  Widget _lineCard(SalesInvoiceDetailLine line) {
    final name = line.itemName.isNotEmpty ? line.itemName : line.itemCode;
    final subtitle = [
      if (line.itemCode.isNotEmpty && line.itemName.isNotEmpty) 'Code ${line.itemCode}',
      if (line.uom.isNotEmpty) line.uom,
    ].join(' · ');
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EAED)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: const Color(0xFFE3F2FD),
              borderRadius: BorderRadius.circular(10),
            ),
            alignment: Alignment.center,
            child: Text(
              '${line.lineNo}',
              style: const TextStyle(fontWeight: FontWeight.w800, color: _accent, fontSize: 13),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                ),
                if (subtitle.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(subtitle, style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
                ],
                const SizedBox(height: 6),
                Text(
                  '${_fmtQty(line.qty)} × ${line.rate.toStringAsFixed(2)}'
                  '${line.discount > 0 ? ' (−${line.discount.toStringAsFixed(2)} disc)' : ''}',
                  style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(
            line.amount.toStringAsFixed(2),
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: Color(0xFF262C50)),
          ),
        ],
      ),
    );
  }
}
