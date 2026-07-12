package ru.fepra.connect

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.health.connect.client.PermissionController
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private val scope = MainScope()
    private lateinit var prefs: Prefs
    private lateinit var status: TextView

    private val permLauncher =
        registerForActivityResult(PermissionController.createRequestPermissionResultContract()) { granted ->
            if (granted.containsAll(HealthReader.PERMISSIONS)) {
                SyncWorker.schedule(this)
                SyncWorker.syncNow(this)
                status.text = "Подключено, первый синк пошёл"
            } else {
                status.text = "Дай доступ к данным Health Connect"
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        prefs = Prefs(this)
        status = findViewById(R.id.status)
        val baseUrl = findViewById<EditText>(R.id.base_url)
        val token = findViewById<EditText>(R.id.token)
        baseUrl.setText(prefs.baseUrl)
        prefs.token?.let { token.setText(it) }
        refreshStatus()

        findViewById<Button>(R.id.btn_connect).setOnClickListener {
            val url = baseUrl.text.toString().trim().trimEnd('/')
            val tok = token.text.toString().trim()
            if (url.isEmpty() || tok.isEmpty()) {
                toast("Заполни сервер и токен"); return@setOnClickListener
            }
            if (HealthReader.client(this) == null) {
                status.text = "Health Connect недоступен на этом телефоне"; return@setOnClickListener
            }
            prefs.baseUrl = url
            prefs.token = tok
            scope.launch {
                val ok = withContext(Dispatchers.IO) {
                    try { ApiClient(prefs.baseUrl, tok).verify() } catch (e: Exception) { false }
                }
                if (ok) permLauncher.launch(HealthReader.PERMISSIONS)
                else status.text = "Токен не принят, проверь его в боте"
            }
        }

        findViewById<Button>(R.id.btn_sync).setOnClickListener {
            if (prefs.token == null) { toast("Сначала подключись"); return@setOnClickListener }
            SyncWorker.syncNow(this)
            toast("Синк поставлен")
        }
    }

    override fun onResume() {
        super.onResume()
        refreshStatus()
    }

    private fun refreshStatus() {
        status.text = prefs.lastSyncIso?.let { "Последний синк: $it" }
            ?: "Не синхронизировано"
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
}
