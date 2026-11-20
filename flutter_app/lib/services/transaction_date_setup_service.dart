import '../core/network/api_client.dart';

class TxnDateLocation {
  TxnDateLocation({required this.code, required this.label, this.name = ''});

  final int code;
  final String label;
  final String name;

  factory TxnDateLocation.fromJson(Map<String, dynamic> json) => TxnDateLocation(
        code: int.tryParse('${json['code'] ?? 0}') ?? 0,
        label: '${json['label'] ?? json['code'] ?? ''}'.trim(),
        name: '${json['name'] ?? ''}'.trim(),
      );
}

class TxnDateModule {
  TxnDateModule({
    required this.key,
    required this.label,
    required this.transactionCode,
    required this.transactionName,
    this.dateFrom = '',
    this.dateTo = '',
    this.openFlag = '',
    this.minDate = '',
    this.isClosed = false,
    this.openedBy = '',
  });

  final String key;
  final String label;
  final int transactionCode;
  final String transactionName;
  String dateFrom;
  String dateTo;
  final String openFlag;
  final String minDate;
  final bool isClosed;
  final String openedBy;

  bool get isOpen => openFlag.toUpperCase() == 'O';

  factory TxnDateModule.fromJson(Map<String, dynamic> json) => TxnDateModule(
        key: '${json['key'] ?? ''}'.trim(),
        label: '${json['label'] ?? ''}'.trim(),
        transactionCode: int.tryParse('${json['transaction_code'] ?? 0}') ?? 0,
        transactionName: '${json['transaction_name'] ?? json['label'] ?? ''}'.trim(),
        dateFrom: '${json['date_from'] ?? json['date_of_open'] ?? ''}'.trim(),
        dateTo: '${json['date_to'] ?? json['date_of_to'] ?? json['date_from'] ?? ''}'.trim(),
        openFlag: '${json['open_flag'] ?? ''}'.trim().toUpperCase(),
        minDate: '${json['min_date'] ?? ''}'.trim(),
        isClosed: json['is_closed'] == true || '${json['open_flag'] ?? ''}'.toUpperCase() == 'C',
        openedBy: '${json['opened_by'] ?? ''}'.trim(),
      );
}

class TxnDateSetupBootstrap {
  TxnDateSetupBootstrap({
    required this.locationCode,
    required this.mode,
    required this.allDateFrom,
    required this.allDateTo,
    required this.allowAnyDate,
    required this.minDate,
    required this.today,
    required this.modules,
    required this.locations,
    this.closedPeriods = const [],
    this.message = '',
    this.warnings = const [],
  });

  final int locationCode;
  final String mode;
  final String allDateFrom;
  final String allDateTo;
  final bool allowAnyDate;
  final String minDate;
  final String today;
  final List<TxnDateModule> modules;
  final List<TxnDateLocation> locations;
  final List<Map<String, dynamic>> closedPeriods;
  final String message;
  final List<String> warnings;

  factory TxnDateSetupBootstrap.fromJson(Map<String, dynamic> json) => TxnDateSetupBootstrap(
        locationCode: int.tryParse('${json['location_code'] ?? 0}') ?? 0,
        mode: '${json['mode'] ?? 'all'}'.trim().toLowerCase(),
        allDateFrom: '${json['all_date_from'] ?? json['all_date'] ?? ''}'.trim(),
        allDateTo: '${json['all_date_to'] ?? json['all_date_from'] ?? json['all_date'] ?? ''}'.trim(),
        allowAnyDate: json['allow_any_date'] == true || json['can_change_any_date'] == true,
        minDate: '${json['min_date'] ?? ''}'.trim(),
        today: '${json['today'] ?? ''}'.trim(),
        modules: (json['modules'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => TxnDateModule.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
        locations: (json['locations'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => TxnDateLocation.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
        closedPeriods: (json['closed_periods'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList(),
        message: '${json['message'] ?? ''}'.trim(),
        warnings: (json['warnings'] as List<dynamic>? ?? const [])
            .map((e) => '$e'.trim())
            .where((e) => e.isNotEmpty)
            .toList(),
      );
}

class TransactionDateSetupService {
  TransactionDateSetupService(this._apiClient);

  final ApiClient _apiClient;

  Future<TxnDateSetupBootstrap> getBootstrap({int? locationCode}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/setup/transaction-date',
      queryParameters: {
        if (locationCode != null && locationCode > 0) 'location_code': locationCode,
      },
    );
    final root = response.data as Map<String, dynamic>;
    final data = root['data'];
    if (data is! Map) throw Exception('Invalid transaction date setup response.');
    return TxnDateSetupBootstrap.fromJson(Map<String, dynamic>.from(data));
  }

  Future<TxnDateSetupBootstrap> save(Map<String, dynamic> payload) async {
    final response = await _apiClient.dio.post('/api/v1/setup/transaction-date', data: payload);
    final root = response.data as Map<String, dynamic>;
    final data = root['data'];
    if (data is! Map) throw Exception('Invalid save response.');
    final boot = TxnDateSetupBootstrap.fromJson(Map<String, dynamic>.from(data));
    final msg = '${root['message'] ?? boot.message}'.trim();
    if (msg.isNotEmpty && boot.message.isEmpty) {
      return TxnDateSetupBootstrap(
        locationCode: boot.locationCode,
        mode: boot.mode,
        allDateFrom: boot.allDateFrom,
        allDateTo: boot.allDateTo,
        allowAnyDate: boot.allowAnyDate,
        minDate: boot.minDate,
        today: boot.today,
        modules: boot.modules,
        locations: boot.locations,
        closedPeriods: boot.closedPeriods,
        message: msg,
        warnings: boot.warnings,
      );
    }
    return boot;
  }

  Future<TxnDateSetupBootstrap> close(Map<String, dynamic> payload) async {
    final response = await _apiClient.dio.post('/api/v1/setup/transaction-date/close', data: payload);
    final root = response.data as Map<String, dynamic>;
    final data = root['data'];
    if (data is! Map) throw Exception('Invalid close response.');
    final boot = TxnDateSetupBootstrap.fromJson(Map<String, dynamic>.from(data));
    final msg = '${root['message'] ?? boot.message}'.trim();
    if (msg.isNotEmpty && boot.message.isEmpty) {
      return TxnDateSetupBootstrap(
        locationCode: boot.locationCode,
        mode: boot.mode,
        allDateFrom: boot.allDateFrom,
        allDateTo: boot.allDateTo,
        allowAnyDate: boot.allowAnyDate,
        minDate: boot.minDate,
        today: boot.today,
        modules: boot.modules,
        locations: boot.locations,
        closedPeriods: boot.closedPeriods,
        message: msg,
        warnings: boot.warnings,
      );
    }
    return boot;
  }
}
