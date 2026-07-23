// Cross-framework GUI benchmark - Flutter/Impeller variant.
//
// One binary implements all four bench apps (hello / list / forms /
// textview). The app VARIANT is chosen from the executable's basename
// (the harness invokes hardlinks bench_flutter_<app> that all point at
// the single built runner ELF, so `data/` + `lib/` resolve next to it),
// and the MODE from the first CLI argument. See the repo README for the
// shared spec and results.md for the fairness caveats.
//
// CLI contract (identical semantics to the egui/iced/qt/gtk variants):
//   --startup       print `first_frame`, then `startup_ms: <float>`
//                   (Dart main entry -> first rendered frame), then exit
//   --scroll-bench  (list/textview) animate scroll at 1000 px/s from the
//                   first frame, record a timestamp per frame, and after
//                   BENCH_SCROLL_SECONDS print one delta (ms) per line +
//                   `done` (then keep running for the memory sample)
//   --interact      (forms) 4 cycles x (40-step focus walk + 20-step
//                   toggle-all), one step / 16 ms; per-frame deltas + `done`
//   (no arg)        run normally (idle-RSS sampling)
//
// Frame pump: like the Qt/GTK retained-mode variants, a periodic driver
// (a `Timer`, analogous to Qt's QTimer / GTK's tick callback) advances
// the animation/steps and marks the tree dirty every tick, so a fresh
// full-surface frame is committed each vsync and the nested headless
// compositor keeps delivering frame callbacks (a bare vsync `Ticker`
// stalls here when a frame carries no damage). Per-frame timestamps come
// from a `SchedulerBinding` persistent frame callback (one per rendered
// frame - Flutter's paint-callback analogue), stamped with a
// process-monotonic Stopwatch (the CLOCK_MONOTONIC family every other
// framework uses). First-frame proxy: the first post-frame callback.

import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

/// Process-monotonic stopwatch. Started explicitly at the first line of
/// `main` (top-level finals are lazily initialized on first *access*, so
/// relying on the initializer would start the clock at the first frame,
/// not at main entry - self_ms would read ~0).
late final Stopwatch _sw;

const double kSpeed = 1000.0; // px/s
const int kRows = 10000;
const double kRowH = 36.0;
const double kStepS = 0.016;
const double kSettleS = 0.5;
const int kDriveMs = 6; // driver period (< vsync, like Qt's timers)

enum Mode { normal, startup, scroll, interact }

Mode _parseMode(List<String> args) {
  final a = args.isNotEmpty ? args.first : '';
  switch (a) {
    case '--startup':
      return Mode.startup;
    case '--scroll-bench':
      return Mode.scroll;
    case '--interact':
      return Mode.interact;
    default:
      return Mode.normal;
  }
}

String _variant() {
  final exe = File(Platform.resolvedExecutable).uri.pathSegments.last;
  for (final v in ['hello', 'list', 'forms', 'textview']) {
    if (exe.contains(v)) return v;
  }
  return 'hello';
}

double _scrollSeconds() =>
    double.tryParse(Platform.environment['BENCH_SCROLL_SECONDS'] ?? '') ?? 6.0;

int _interactCycles() =>
    int.tryParse(Platform.environment['BENCH_INTERACT_CYCLES'] ?? '') ?? 4;

String _loadCorpus() {
  final path = Platform.environment['BENCH_CORPUS'] ?? 'harness/out/corpus.txt';
  return File(path).readAsStringSync();
}

double _bounce(double dist, double max) {
  if (max <= 0.0) return 0.0;
  final period = 2.0 * max;
  final m = dist % period;
  return m < max ? m : period - m;
}

/// Dump per-frame deltas (from recorded monotonic microsecond stamps) +
/// `done`, then KEEP RUNNING (the harness samples post-run memory from
/// the still-live process, then kills it). One write + one flush so no
/// second write races an in-flight flush Future.
void _printDeltasDone(List<int> frameMicros) {
  final b = StringBuffer();
  for (var i = 1; i < frameMicros.length; i++) {
    final ms = (frameMicros[i] - frameMicros[i - 1]) / 1000.0;
    b.writeln(ms.toStringAsFixed(3));
  }
  b.writeln('done');
  stdout.write(b.toString());
  stdout.flush();
}

void main(List<String> args) {
  _sw = Stopwatch()..start();
  final mode = _parseMode(args);
  final variant = _variant();
  final corpus = variant == 'textview' ? _loadCorpus() : '';
  WidgetsFlutterBinding.ensureInitialized();
  runApp(BenchApp(
    mode: mode,
    variant: variant,
    corpus: corpus,
    scrollSeconds: _scrollSeconds(),
    interactCycles: _interactCycles(),
  ));
}

class BenchApp extends StatelessWidget {
  final Mode mode;
  final String variant;
  final String corpus;
  final double scrollSeconds;
  final int interactCycles;

  const BenchApp({
    super.key,
    required this.mode,
    required this.variant,
    required this.corpus,
    required this.scrollSeconds,
    required this.interactCycles,
  });

  @override
  Widget build(BuildContext context) {
    Widget home;
    switch (variant) {
      case 'list':
        home = ListPage(mode: mode, scrollSeconds: scrollSeconds);
        break;
      case 'forms':
        home = FormsPage(mode: mode, cycles: interactCycles);
        break;
      case 'textview':
        home = TextViewPage(
            mode: mode, scrollSeconds: scrollSeconds, corpus: corpus);
        break;
      default:
        home = HelloPage(mode: mode);
    }
    return MaterialApp(
      title: 'Bench',
      debugShowCheckedModeBanner: false,
      theme:
          ThemeData(useMaterial3: false, visualDensity: VisualDensity.compact),
      home: Scaffold(body: home),
    );
  }
}

/// Reports the first rendered frame (spawn->marker proxy for the harness)
/// and, in --startup mode, the main->first-frame self time, then exits.
mixin FirstFrameReporter<T extends StatefulWidget> on State<T> {
  bool _firstDone = false;

  void reportFirstFrame(Mode mode, {VoidCallback? onFirst}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_firstDone) return;
      _firstDone = true;
      if (mode == Mode.startup) {
        // main entry -> first presented frame. Single write, then flush,
        // then exit once the flush future completes (writing during an
        // in-flight flush throws "StreamSink is bound to a stream").
        final ms = _sw.elapsedMicroseconds / 1000.0;
        stdout.write('first_frame\nstartup_ms: ${ms.toStringAsFixed(3)}\n');
        stdout.flush().whenComplete(() => exit(0));
        return;
      }
      stdout.write('first_frame\n');
      stdout.flush();
      if (onFirst != null) onFirst();
    });
  }
}

/// Timer-driven bench pass with per-frame recording (see the file header).
mixin BenchPass<T extends StatefulWidget> on State<T> {
  final List<int> _frames = [];
  bool _recording = false;
  bool _passDone = false;
  Timer? _driveTimer;
  int _firstFrameMicros = 0;
  int _recordStartMicros = 0;
  int _heartbeat = 0;

  void _persistentFrame(Duration _) {
    if (_recording && !_passDone) _frames.add(_sw.elapsedMicroseconds);
  }

  /// Begin driving at the first frame. `tick` runs every kDriveMs.
  void beginPass() {
    _firstFrameMicros = _sw.elapsedMicroseconds;
    SchedulerBinding.instance.addPersistentFrameCallback(_persistentFrame);
    _driveTimer =
        Timer.periodic(const Duration(milliseconds: kDriveMs), (_) {
      if (_passDone) return;
      tick();
    });
  }

  double get sinceFirstFrameS =>
      (_sw.elapsedMicroseconds - _firstFrameMicros) / 1e6;

  double get sinceRecordS =>
      (_sw.elapsedMicroseconds - _recordStartMicros) / 1e6;

  void startRecording() {
    _recording = true;
    _recordStartMicros = _sw.elapsedMicroseconds;
  }

  /// Keeps the frame pump alive without semantic change (headless
  /// compositor stops delivering frame callbacks if a vsync carries no
  /// committed frame; a dirty setState forces a full-surface commit).
  void pumpHeartbeat() {
    setState(() => _heartbeat++);
  }

  void finishPass() {
    _passDone = true;
    _recording = false;
    _driveTimer?.cancel();
    _printDeltasDone(_frames);
  }

  /// Subclass hook: advance the animation/steps, mark the tree dirty, and
  /// call finishPass() when the workload completes.
  void tick();

  void disposePass() {
    _driveTimer?.cancel();
  }
}

// --------------------------------------------------------------------------
// hello
// --------------------------------------------------------------------------

class HelloPage extends StatefulWidget {
  final Mode mode;
  const HelloPage({super.key, required this.mode});
  @override
  State<HelloPage> createState() => _HelloPageState();
}

class _HelloPageState extends State<HelloPage> with FirstFrameReporter {
  @override
  void initState() {
    super.initState();
    reportFirstFrame(widget.mode);
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('Hello',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
          const SizedBox(height: 12),
          ElevatedButton(onPressed: () {}, child: const Text('Press')),
        ],
      ),
    );
  }
}

// --------------------------------------------------------------------------
// list - 10,000-row virtualized ListView.builder
// --------------------------------------------------------------------------

class ListPage extends StatefulWidget {
  final Mode mode;
  final double scrollSeconds;
  const ListPage({super.key, required this.mode, required this.scrollSeconds});
  @override
  State<ListPage> createState() => _ListPageState();
}

class _ListPageState extends State<ListPage>
    with FirstFrameReporter, BenchPass {
  final ScrollController _ctrl = ScrollController();
  int _count = 0;
  double _slider = 50;

  @override
  void initState() {
    super.initState();
    reportFirstFrame(widget.mode, onFirst: () {
      if (widget.mode == Mode.scroll) {
        startRecording();
        beginPass();
      }
    });
  }

  @override
  void tick() {
    final elapsed = sinceRecordS;
    if (elapsed >= widget.scrollSeconds) {
      finishPass();
      return;
    }
    final max = kRows * kRowH - _ctrl.position.viewportDimension;
    // jumpTo damages the list (new visible rows) => full-surface commit.
    _ctrl.jumpTo(_bounce(kSpeed * elapsed, max).clamp(0.0, max));
  }

  @override
  void dispose() {
    disposePass();
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        SizedBox(
          height: 48,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              children: [
                const Text('Bench',
                    style:
                        TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
                const Spacer(),
                OutlinedButton(
                  onPressed: () => setState(() => _count++),
                  child: Text('Count: $_count'),
                ),
              ],
            ),
          ),
        ),
        Expanded(
          child: ListView.builder(
            controller: _ctrl,
            itemExtent: kRowH,
            itemCount: kRows,
            physics: const ClampingScrollPhysics(),
            itemBuilder: (context, i) => Padding(
              padding: const EdgeInsets.only(left: 8),
              child: Row(
                children: [
                  Text('Item $i',
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(width: 12),
                  Text('subtitle $i',
                      style: const TextStyle(color: Color(0xFF777777))),
                ],
              ),
            ),
          ),
        ),
        SizedBox(
          height: 56,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              children: [
                const SizedBox(
                  width: 240,
                  child: TextField(
                    decoration: InputDecoration(hintText: 'Type here...'),
                  ),
                ),
                SizedBox(
                  width: 200,
                  child: Slider(
                    min: 0,
                    max: 100,
                    value: _slider,
                    onChanged: (v) => setState(() => _slider = v),
                  ),
                ),
                Text('${_slider.round()}'),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

// --------------------------------------------------------------------------
// textview - full corpus as one wrapped Text in a scroll view
// --------------------------------------------------------------------------

class TextViewPage extends StatefulWidget {
  final Mode mode;
  final double scrollSeconds;
  final String corpus;
  const TextViewPage(
      {super.key,
      required this.mode,
      required this.scrollSeconds,
      required this.corpus});
  @override
  State<TextViewPage> createState() => _TextViewPageState();
}

class _TextViewPageState extends State<TextViewPage>
    with FirstFrameReporter, BenchPass {
  final ScrollController _ctrl = ScrollController();

  @override
  void initState() {
    super.initState();
    reportFirstFrame(widget.mode, onFirst: () {
      if (widget.mode == Mode.scroll) {
        startRecording();
        beginPass();
      }
    });
  }

  @override
  void tick() {
    final elapsed = sinceRecordS;
    if (elapsed >= widget.scrollSeconds) {
      finishPass();
      return;
    }
    final max = _ctrl.position.maxScrollExtent;
    _ctrl.jumpTo(_bounce(kSpeed * elapsed, max).clamp(0.0, max));
  }

  @override
  void dispose() {
    disposePass();
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        SizedBox(
          height: 48,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              children: const [
                Text('Bench',
                    style:
                        TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
              ],
            ),
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            controller: _ctrl,
            physics: const ClampingScrollPhysics(),
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: Text(widget.corpus, softWrap: true),
            ),
          ),
        ),
      ],
    );
  }
}

// --------------------------------------------------------------------------
// forms - ~40-control settings page + interact driver
// --------------------------------------------------------------------------

const List<String> _radioA = ['System', 'Light', 'Dark', 'High contrast'];
const List<String> _radioB = ['Off', 'Crash reports only', 'Basic', 'Full'];
const List<List<String>> _dropOpts = [
  ['Compact', 'Cozy', 'Normal', 'Comfortable', 'Spacious'],
  ['Auto', 'HTTP/1.1', 'HTTP/2', 'HTTP/3', 'SOCKS5'],
  ['Auto', 'LF', 'CRLF', 'CR', 'Keep mixed'],
  ['Error', 'Warn', 'Info', 'Debug', 'Trace'],
];

class FormsPage extends StatefulWidget {
  final Mode mode;
  final int cycles;
  const FormsPage({super.key, required this.mode, required this.cycles});
  @override
  State<FormsPage> createState() => _FormsPageState();
}

class _FormsPageState extends State<FormsPage>
    with FirstFrameReporter, BenchPass {
  final ScrollController _scroll = ScrollController();

  final List<TextEditingController> _inputs =
      List.generate(8, (_) => TextEditingController());
  final List<FocusNode> _focus = List.generate(40, (_) => FocusNode());
  final List<bool> _checks = List.filled(8, false);
  final List<bool> _toggles = List.filled(4, false);
  int _radioAIdx = 0, _radioBIdx = 0;
  final List<double> _sliders = List.filled(4, 50);
  final List<int> _drops = List.filled(4, 0);
  String _status = 'idle';

  static const int _stepsPerCycle = 60; // 40 focus + 20 toggle
  int _stepDone = 0;
  int _totalSteps = 0;

  int _fi = 0; // focus-node cursor while building
  int _inputCounter = 0;
  int _toggleCounter = 0;

  @override
  void initState() {
    super.initState();
    _totalSteps = _stepsPerCycle * widget.cycles;
    reportFirstFrame(widget.mode, onFirst: () {
      if (widget.mode == Mode.interact) beginPass();
    });
  }

  @override
  void tick() {
    if (!_recording) {
      // Settle phase: keep the pump alive, start recording after kSettleS.
      pumpHeartbeat();
      if (sinceFirstFrameS >= kSettleS) {
        startRecording();
        _focus[0].requestFocus();
      }
      return;
    }
    var due = (sinceRecordS / kStepS).floor();
    if (due > _totalSteps) due = _totalSteps;
    setState(() {
      // Status text changes every tick so each recorded frame carries
      // damage (matches Qt: the per-step status label repaint marks frames).
      _status = 'step $_stepDone';
      while (_stepDone < due) {
        _applyStep(_stepDone);
        _stepDone++;
      }
      _heartbeat++;
    });
    if (_stepDone >= _totalSteps) finishPass();
  }

  void _applyStep(int step) {
    final inCycle = step % _stepsPerCycle;
    if (inCycle < 40) {
      // Focus walk: advance the real focus chain (Tab equivalent).
      _focus[inCycle % _focus.length].requestFocus();
    } else {
      final t = inCycle - 40;
      if (t <= 7) {
        _checks[t] = !_checks[t];
      } else if (t <= 11) {
        _toggles[t - 8] = !_toggles[t - 8];
      } else if (t <= 15) {
        _radioAIdx = (_radioAIdx + 1) % 4;
      } else {
        _radioBIdx = (_radioBIdx + 1) % 4;
      }
    }
  }

  @override
  void dispose() {
    disposePass();
    _scroll.dispose();
    for (final c in _inputs) {
      c.dispose();
    }
    for (final f in _focus) {
      f.dispose();
    }
    super.dispose();
  }

  Widget _input(String label, String hint, {double width = 220}) {
    final node = _focus[_fi++];
    final ctrl = _inputs[_inputCounter++];
    return Row(children: [
      SizedBox(width: 110, child: Text(label)),
      SizedBox(
        width: width,
        child: TextField(
          focusNode: node,
          controller: ctrl,
          decoration: InputDecoration(
              hintText: hint,
              isDense: true,
              border: const OutlineInputBorder()),
        ),
      ),
    ]);
  }

  Widget _check(String label, int idx) {
    final node = _focus[_fi++];
    return Focus(
      focusNode: node,
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Checkbox(
            value: _checks[idx],
            onChanged: (v) => setState(() => _checks[idx] = v ?? false)),
        Text(label),
      ]),
    );
  }

  Widget _toggle(String label) {
    final node = _focus[_fi++];
    final idx = _toggleCounter++;
    return Row(children: [
      SizedBox(width: 110, child: Text(label)),
      Focus(
        focusNode: node,
        child: Switch(
            value: _toggles[idx],
            onChanged: (v) => setState(() => _toggles[idx] = v)),
      ),
    ]);
  }

  Widget _radioCol(List<String> names, int groupSel, void Function(int) onSel) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < names.length; i++)
          Focus(
            focusNode: _focus[_fi++],
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Radio<int>(
                  value: i,
                  groupValue: groupSel,
                  onChanged: (v) => onSel(v ?? 0)),
              Text(names[i]),
            ]),
          ),
      ],
    );
  }

  Widget _sliderRow(String label, int idx) {
    final node = _focus[_fi++];
    return Row(children: [
      SizedBox(width: 110, child: Text(label)),
      SizedBox(
        width: 200,
        child: Focus(
          focusNode: node,
          child: Slider(
              min: 0,
              max: 100,
              value: _sliders[idx],
              onChanged: (v) => setState(() => _sliders[idx] = v)),
        ),
      ),
    ]);
  }

  Widget _dropdown(String label, int idx) {
    final node = _focus[_fi++];
    return Row(children: [
      SizedBox(width: 110, child: Text(label)),
      Focus(
        focusNode: node,
        child: DropdownButton<int>(
          value: _drops[idx],
          items: [
            for (var i = 0; i < _dropOpts[idx].length; i++)
              DropdownMenuItem(value: i, child: Text(_dropOpts[idx][i])),
          ],
          onChanged: (v) => setState(() => _drops[idx] = v ?? 0),
        ),
      ),
    ]);
  }

  Widget _button(String text) {
    final node = _focus[_fi++];
    return Focus(
      focusNode: node,
      child: OutlinedButton(onPressed: () {}, child: Text(text)),
    );
  }

  Widget _group(String title, List<Widget> rows) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            ...rows.map((r) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: r,
                )),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Reset per-build cursors so node/controller assignment is stable.
    _fi = 0;
    _inputCounter = 0;
    _toggleCounter = 0;
    return Column(
      children: [
        SizedBox(
          height: 48,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(children: const [
              Text('Bench',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
            ]),
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            controller: _scroll,
            padding: const EdgeInsets.all(8),
            child: Column(
              children: [
                _group('Account', [
                  _input('Username:', 'Username'),
                  _input('Email:', 'Email'),
                  Row(children: [
                    _check('Remember me', 0),
                    const SizedBox(width: 12),
                    _check('Subscribe to newsletter', 1),
                  ]),
                  _button('Sign out'),
                ]),
                _group('Appearance', [
                  Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const SizedBox(width: 110, child: Text('Theme:')),
                    _radioCol(_radioA, _radioAIdx,
                        (v) => setState(() => _radioAIdx = v)),
                  ]),
                  _sliderRow('Font size:', 0),
                  _dropdown('Density:', 0),
                  _toggle('Animations:'),
                ]),
                _group('Network', [
                  _input('Proxy host:', 'proxy.example.com'),
                  _input('Proxy port:', '8080', width: 100),
                  Row(children: [
                    _check('Use proxy', 2),
                    const SizedBox(width: 12),
                    _check('Verify TLS certificates', 3),
                  ]),
                  _sliderRow('Timeout:', 1),
                  _dropdown('Protocol:', 1),
                  _button('Test connection'),
                ]),
                _group('Editor', [
                  _input('Font family:', 'monospace'),
                  _input('Tab width:', '4', width: 100),
                  Row(children: [
                    _check('Word wrap', 4),
                    const SizedBox(width: 12),
                    _check('Line numbers', 5),
                  ]),
                  _dropdown('Line endings:', 2),
                  _sliderRow('Rulers:', 2),
                  _toggle('Autosave:'),
                ]),
                _group('Privacy', [
                  Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const SizedBox(width: 110, child: Text('Telemetry:')),
                    _radioCol(_radioB, _radioBIdx,
                        (v) => setState(() => _radioBIdx = v)),
                  ]),
                  Row(children: [
                    _check('Upload crash reports', 6),
                    const SizedBox(width: 12),
                    _check('Share usage statistics', 7),
                  ]),
                  _toggle('Do not track:'),
                  _button('Clear data'),
                ]),
                _group('Advanced', [
                  _input('Config path:', '~/.config/bench'),
                  _input('Log filter:', 'info'),
                  _dropdown('Log level:', 3),
                  _sliderRow('Cache size:', 3),
                  _toggle('Experimental:'),
                  _button('Reset all'),
                ]),
              ],
            ),
          ),
        ),
        // Footer status labels - change every interact step (visible damage).
        SizedBox(
          height: 32,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(children: [
              Text(_status, style: const TextStyle(color: Color(0xFF777777))),
              const SizedBox(width: 12),
              Text('theme: ${_radioA[_radioAIdx]}',
                  style: const TextStyle(color: Color(0xFF777777))),
              const SizedBox(width: 12),
              Text('telemetry: ${_radioB[_radioBIdx]}',
                  style: const TextStyle(color: Color(0xFF777777))),
            ]),
          ),
        ),
      ],
    );
  }
}
