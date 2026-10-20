import 'package:flutter_test/flutter_test.dart';
import 'package:isilo_recovery/main.dart';

void main() {
  testWidgets('App launches', (WidgetTester tester) async {
    await tester.pumpWidget(const IsiloRecoveryApp());
    expect(find.text('iSilo Recovery'), findsOneWidget);
  });
}
