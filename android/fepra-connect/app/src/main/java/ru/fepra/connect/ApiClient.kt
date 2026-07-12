package ru.fepra.connect

import java.util.concurrent.TimeUnit
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

class ApiClient(private val baseUrl: String, private val token: String) {
    private val http = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()
    private val json = "application/json; charset=utf-8".toMediaType()

    fun verify(): Boolean = post("/ingest/samsung/verify", "{}")

    fun sync(payload: String): Boolean = post("/ingest/samsung", payload)

    private fun post(path: String, body: String): Boolean {
        val req = Request.Builder()
            .url(baseUrl + path)
            .header("Authorization", "Bearer $token")
            .post(body.toRequestBody(json))
            .build()
        http.newCall(req).execute().use { resp -> return resp.isSuccessful }
    }
}
