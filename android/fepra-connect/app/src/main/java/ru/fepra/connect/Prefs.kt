package ru.fepra.connect

import android.content.Context

class Prefs(ctx: Context) {
    private val sp = ctx.getSharedPreferences("fepra", Context.MODE_PRIVATE)

    var baseUrl: String
        get() = sp.getString("base_url", "")!!
        set(v) = sp.edit().putString("base_url", v.trimEnd('/')).apply()

    var token: String?
        get() = sp.getString("token", null)
        set(v) = sp.edit().putString("token", v).apply()

    var lastSyncIso: String?
        get() = sp.getString("last_sync", null)
        set(v) = sp.edit().putString("last_sync", v).apply()
}
