import '../../services/sales_service.dart';

/// Header chosen on the AI Sales setup page (before voice).
class SalesAiSessionHeader {
  const SalesAiSessionHeader({
    required this.billingType,
    required this.walkIn,
    required this.features,
    this.customer,
    this.warehouse,
    this.address = '',
    this.orderNo = '',
    this.remarks = '',
    this.billno = '',
    this.billDate = '',
    this.billTime = '',
    this.locationName = '',
  });

  final String billingType; // CASH | CREDIT
  final bool walkIn;
  final SalesCustomerOption? customer;
  final SalesWarehouseOption? warehouse;
  final String address;
  final String orderNo;
  final String remarks;
  final String billno;
  final String billDate;
  final String billTime;
  final String locationName;
  final SalesInvoiceFeatures features;

  String get warehouseId => warehouse?.warehouseId ?? '';
  String get customerCode => walkIn ? '' : (customer?.code ?? '');
}
