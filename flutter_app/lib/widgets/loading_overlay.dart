import 'package:flutter/material.dart';

/// Dims [child] and shows a centered [CircularProgressIndicator] while [loading].
class LoadingOverlay extends StatelessWidget {
  const LoadingOverlay({
    required this.loading,
    required this.child,
    this.message,
    super.key,
  });

  final bool loading;
  final Widget child;
  final String? message;

  @override
  Widget build(BuildContext context) {
    if (!loading) return child;
    return Stack(
      alignment: Alignment.center,
      children: [
        child,
        Positioned.fill(
          child: AbsorbPointer(
            child: ColoredBox(
              color: Colors.black.withValues(alpha: 0.35),
              child: Center(
                child: Material(
                  color: Colors.white,
                  elevation: 4,
                  borderRadius: BorderRadius.circular(12),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const SizedBox(
                          width: 36,
                          height: 36,
                          child: CircularProgressIndicator(strokeWidth: 3),
                        ),
                        if (message != null && message!.isNotEmpty) ...[
                          const SizedBox(height: 16),
                          Text(
                            message!,
                            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                  fontWeight: FontWeight.w600,
                                ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
