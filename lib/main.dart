import 'package:flutter/material.dart';
import 'screens/home_screen.dart';

void main() {
  runApp(const IsiloRecoveryApp());
}

class IsiloRecoveryApp extends StatelessWidget {
  const IsiloRecoveryApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'iSilo Recovery',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1A237E),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}
