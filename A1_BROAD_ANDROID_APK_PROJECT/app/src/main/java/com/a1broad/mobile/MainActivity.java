package com.a1broad.mobile;

import android.app.Activity;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import java.io.File;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private EditText tokenInput;
    private EditText daysInput;
    private TextView output;
    private SharedPreferences prefs;
    private PyObject bridge;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("a1", MODE_PRIVATE);
        bridge = Python.getInstance().getModule("mobile_bridge");
        setContentView(buildUi());
        showStrategy();
    }

    private View buildUi() {
        int p = dp(16);
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(p, p, p, p);
        scroll.addView(root);

        TextView title = new TextView(this);
        title.setText("A1 Broad BB 2/3/5");
        title.setTextSize(24);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title);

        TextView sub = new TextView(this);
        sub.setText("₹18,261 canonical 60-day research setup • local Android backtesting");
        sub.setTextSize(14);
        sub.setPadding(0, dp(4), 0, dp(14));
        root.addView(sub);

        tokenInput = new EditText(this);
        tokenInput.setHint("Paste fresh Upstox access token");
        tokenInput.setSingleLine(true);
        tokenInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        tokenInput.setText(prefs.getString("token", ""));
        root.addView(tokenInput, matchWrap());

        Button save = button("Save token");
        save.setOnClickListener(v -> {
            String token = tokenInput.getText().toString().trim();
            prefs.edit().putString("token", token).apply();
            append("Token saved securely in this app's private preferences.\n");
        });
        root.addView(save, matchWrap());

        daysInput = new EditText(this);
        daysInput.setHint("Trading days (e.g. 10, 20, 30, 60)");
        daysInput.setInputType(InputType.TYPE_CLASS_NUMBER);
        daysInput.setText("60");
        root.addView(daysInput, matchWrap());

        Button strategy = button("Show selected strategy");
        strategy.setOnClickListener(v -> showStrategy());
        root.addView(strategy, matchWrap());

        Button diag = button("Test Upstox connection");
        diag.setOnClickListener(v -> runTask("Diagnostics", "diagnostics"));
        root.addView(diag, matchWrap());

        Button history = button("Download / discover history");
        history.setOnClickListener(v -> runTask("History download", "history"));
        root.addView(history, matchWrap());

        Button backtest = button("Run canonical backtest");
        backtest.setOnClickListener(v -> runTask("Backtest", "backtest"));
        root.addView(backtest, matchWrap());

        Button cached = button("Show cached days");
        cached.setOnClickListener(v -> runTask("Cached days", "cached"));
        root.addView(cached, matchWrap());

        Button report = button("Show latest report");
        report.setOnClickListener(v -> runTask("Latest report", "report"));
        root.addView(report, matchWrap());

        output = new TextView(this);
        output.setTextSize(13);
        output.setTypeface(Typeface.MONOSPACE);
        output.setTextIsSelectable(true);
        output.setPadding(0, dp(14), 0, dp(40));
        root.addView(output, matchWrap());

        TextView note = new TextView(this);
        note.setText("Keep the app open during large history downloads. This APK is for research/backtesting; real-money order placement is intentionally not enabled in the mobile APK.");
        note.setTextSize(12);
        note.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(note, matchWrap());
        return scroll;
    }

    private void showStrategy() {
        try {
            String s = bridge.callAttr("strategy_summary").toString();
            output.setText(s + "\n");
        } catch (Exception e) {
            output.setText("Python startup error: " + e + "\n");
        }
    }

    private void runTask(String label, String type) {
        String token = tokenInput.getText().toString().trim();
        prefs.edit().putString("token", token).apply();
        int days = 60;
        try { days = Integer.parseInt(daysInput.getText().toString().trim()); } catch (Exception ignored) {}
        final int fDays = Math.max(1, days);
        final String base = new File(getFilesDir(), "a1data").getAbsolutePath();
        append("\n=== " + label + " ===\n");
        setBusy(true);
        executor.submit(() -> {
            String result;
            try {
                if (type.equals("diagnostics")) {
                    result = bridge.callAttr("diagnostics", base, token).toString();
                } else if (type.equals("history")) {
                    result = bridge.callAttr("download_history", base, token, fDays).toString();
                } else if (type.equals("backtest")) {
                    result = bridge.callAttr("run_backtest", base, fDays).toString();
                } else if (type.equals("cached")) {
                    result = bridge.callAttr("cached_days", base).toString();
                } else {
                    result = bridge.callAttr("latest_report", base).toString();
                }
            } catch (Exception e) {
                result = "ERROR: " + e;
            }
            final String finalResult = result;
            runOnUiThread(() -> {
                append(finalResult + "\n");
                setBusy(false);
            });
        });
    }

    private void setBusy(boolean busy) {
        if (busy) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        tokenInput.setEnabled(!busy);
        daysInput.setEnabled(!busy);
    }

    private void append(String text) {
        output.append(text);
    }

    private Button button(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        return b;
    }

    private LinearLayout.LayoutParams matchWrap() {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, dp(4), 0, dp(4));
        return lp;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }
}
