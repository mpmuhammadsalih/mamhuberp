import 'api_error_message.dart';

/// Map API failures to user-facing text for ChangeNotifier providers.
String providerApiError(Object e) => apiErrorMessage(e, authenticatedContext: true);

bool providerAccessDenied(Object? e) => e != null && isAccessDenied(e);
