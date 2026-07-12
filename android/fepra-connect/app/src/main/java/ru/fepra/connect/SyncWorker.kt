package ru.fepra.connect

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.io.IOException
import java.time.Instant
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import ru.fepra.connect.canon.PayloadJson

class SyncWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val prefs = Prefs(applicationContext)
        val token = prefs.token ?: return Result.failure()
        val client = HealthReader.client(applicationContext) ?: return Result.failure()
        val daysBack = if (prefs.lastSyncIso == null) 30L else 7L
        return try {
            val (days, acts) = HealthReader.read(client, daysBack)
            val ok = withContext(Dispatchers.IO) {
                ApiClient(prefs.baseUrl, token).sync(PayloadJson.build(days, acts))
            }
            if (ok) {
                prefs.lastSyncIso = Instant.now().toString()
                Result.success()
            } else Result.retry()
        } catch (e: IOException) {
            Result.retry()
        } catch (e: SecurityException) {
            Result.failure()
        }
    }

    companion object {
        fun schedule(ctx: Context) {
            val net = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
            WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
                "fepra-sync", ExistingPeriodicWorkPolicy.UPDATE,
                PeriodicWorkRequestBuilder<SyncWorker>(6, TimeUnit.HOURS)
                    .setConstraints(net).build())
        }

        fun syncNow(ctx: Context) {
            WorkManager.getInstance(ctx).enqueue(OneTimeWorkRequestBuilder<SyncWorker>().build())
        }
    }
}
