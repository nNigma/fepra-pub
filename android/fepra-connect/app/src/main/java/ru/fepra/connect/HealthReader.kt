package ru.fepra.connect

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ElevationGainedRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.HeartRateVariabilityRmssdRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.records.RespiratoryRateRecord
import androidx.health.connect.client.records.RestingHeartRateRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.records.Vo2MaxRecord
import androidx.health.connect.client.records.WeightRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import kotlin.reflect.KClass
import ru.fepra.connect.canon.ActivityOut
import ru.fepra.connect.canon.DayOut
import ru.fepra.connect.canon.Mapping
import ru.fepra.connect.canon.StageIv

object HealthReader {
    val PERMISSIONS: Set<String> = setOf(
        HealthPermission.getReadPermission(SleepSessionRecord::class),
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(RestingHeartRateRecord::class),
        HealthPermission.getReadPermission(HeartRateVariabilityRmssdRecord::class),
        HealthPermission.getReadPermission(OxygenSaturationRecord::class),
        HealthPermission.getReadPermission(RespiratoryRateRecord::class),
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(Vo2MaxRecord::class),
        HealthPermission.getReadPermission(WeightRecord::class),
        HealthPermission.getReadPermission(ExerciseSessionRecord::class),
        HealthPermission.getReadPermission(DistanceRecord::class),
        HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(TotalCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(ElevationGainedRecord::class),
    )

    fun client(ctx: Context): HealthConnectClient? =
        if (HealthConnectClient.getSdkStatus(ctx) == HealthConnectClient.SDK_AVAILABLE)
            HealthConnectClient.getOrCreate(ctx) else null

    private suspend fun <T : Record> readAll(
        c: HealthConnectClient, cls: KClass<T>, from: Instant, to: Instant,
    ): List<T> {
        val out = mutableListOf<T>()
        var token: String? = null
        do {
            val req = if (token == null)
                ReadRecordsRequest(cls, TimeRangeFilter.between(from, to))
            else
                ReadRecordsRequest(cls, TimeRangeFilter.between(from, to), pageToken = token)
            val resp = c.readRecords(req)
            out += resp.records
            token = resp.pageToken
        } while (!token.isNullOrEmpty())
        return out
    }

    suspend fun read(c: HealthConnectClient, daysBack: Long): Pair<List<DayOut>, List<ActivityOut>> {
        val zone = ZoneId.systemDefault()
        val today = LocalDate.now(zone)
        val from = today.minusDays(daysBack).atStartOfDay(zone).toInstant()
        val to = Instant.now()

        val aggs = sortedMapOf<LocalDate, MutableMap<String, Any?>>()
        fun agg(d: LocalDate) = aggs.getOrPut(d) { mutableMapOf() }
        @Suppress("UNCHECKED_CAST")
        fun nums(d: LocalDate, k: String) = agg(d).getOrPut(k) { mutableListOf<Double>() } as MutableList<Double>

        for (r in readAll(c, SleepSessionRecord::class, from, to)) {
            val day = r.endTime.atZone(zone).toLocalDate()
            val stages = r.stages.map {
                StageIv(
                    Duration.between(r.startTime, it.startTime).seconds,
                    Duration.between(r.startTime, it.endTime).seconds,
                    when (it.stage) {
                        SleepSessionRecord.STAGE_TYPE_DEEP -> "deep"
                        SleepSessionRecord.STAGE_TYPE_REM -> "rem"
                        SleepSessionRecord.STAGE_TYPE_LIGHT -> "light"
                        SleepSessionRecord.STAGE_TYPE_SLEEPING -> "sleep"
                        else -> "awake"
                    })
            }
            val s = Mapping.sleep(stages, Duration.between(r.startTime, r.endTime).seconds)
            val a = agg(day)
            a["sleep_h"] = s.hours
            a["deep"] = s.deepH
            a["rem"] = s.remH
        }
        for (r in readAll(c, RestingHeartRateRecord::class, from, to))
            agg(r.time.atZone(zone).toLocalDate())["rhr"] = r.beatsPerMinute.toInt()
        for (r in readAll(c, HeartRateVariabilityRmssdRecord::class, from, to))
            nums(r.time.atZone(zone).toLocalDate(), "hrv") += r.heartRateVariabilityMillis
        for (r in readAll(c, OxygenSaturationRecord::class, from, to))
            nums(r.time.atZone(zone).toLocalDate(), "spo2") += r.percentage.value
        for (r in readAll(c, RespiratoryRateRecord::class, from, to))
            nums(r.time.atZone(zone).toLocalDate(), "resp") += r.rate
        for (r in readAll(c, StepsRecord::class, from, to)) {
            val d = agg(r.startTime.atZone(zone).toLocalDate())
            d["steps"] = (d["steps"] as? Long ?: 0L) + r.count
        }
        for (r in readAll(c, Vo2MaxRecord::class, from, to))
            agg(r.time.atZone(zone).toLocalDate())["vo2"] = r.vo2MillilitersPerMinuteKilogram
        for (r in readAll(c, WeightRecord::class, from, to))
            agg(r.time.atZone(zone).toLocalDate())["weight"] = Mapping.round1(r.weight.inKilograms)

        val days = aggs.map { (d, a) ->
            @Suppress("UNCHECKED_CAST")
            fun avg(k: String) = (a[k] as? MutableList<Double>)?.takeIf { it.isNotEmpty() }?.let { Mapping.round1(it.average()) }
            @Suppress("UNCHECKED_CAST")
            fun min(k: String) = (a[k] as? MutableList<Double>)?.minOrNull()?.let { Mapping.round1(it) }
            DayOut(
                day = d.toString(),
                sleepH = a["sleep_h"] as? Double,
                restingHr = a["rhr"] as? Int,
                hrv = avg("hrv"),
                spo2Avg = avg("spo2"),
                spo2Lowest = min("spo2"),
                respiration = avg("resp"),
                sleepDeepH = a["deep"] as? Double,
                sleepRemH = a["rem"] as? Double,
                steps = a["steps"] as? Long,
                vo2max = a["vo2"] as? Double,
                weightKg = a["weight"] as? Double,
            )
        }

        val acts = mutableListOf<ActivityOut>()
        for (s in readAll(c, ExerciseSessionRecord::class, from, to)) {
            val durSec = Duration.between(s.startTime, s.endTime).seconds
            val hr = readAll(c, HeartRateRecord::class, s.startTime, s.endTime)
                .flatMap { it.samples }
                .map { longArrayOf(Duration.between(s.startTime, it.time).seconds, it.beatsPerMinute) }
                .sortedBy { it[0] }
            val distKm = readAll(c, DistanceRecord::class, s.startTime, s.endTime)
                .sumOf { it.distance.inKilometers }.takeIf { it > 0 }?.let { Mapping.round1(it) }
            val kcal = readAll(c, ActiveCaloriesBurnedRecord::class, s.startTime, s.endTime)
                .sumOf { it.energy.inKilocalories }.takeIf { it > 0 }
                ?: readAll(c, TotalCaloriesBurnedRecord::class, s.startTime, s.endTime)
                    .sumOf { it.energy.inKilocalories }.takeIf { it > 0 }
            val elev = readAll(c, ElevationGainedRecord::class, s.startTime, s.endTime)
                .sumOf { it.elevation.inMeters }.takeIf { it > 0 }?.let { Mapping.round1(it) }
            acts += ActivityOut(
                activityId = "hc-" + s.metadata.id,
                sport = Mapping.sport(s.exerciseType),
                startIso = s.startTime.atZone(zone).toOffsetDateTime().toString(),
                durationMin = Mapping.round1(durSec / 60.0),
                avgHr = hr.map { it[1] }.takeIf { it.isNotEmpty() }?.average()?.toInt(),
                maxHr = hr.maxOfOrNull { it[1] }?.toInt(),
                calories = kcal?.toInt(),
                distanceKm = distKm,
                elevationGainM = elev,
                paceSecPerKm = Mapping.paceSecPerKm(durSec, distKm),
                hrSeries = Mapping.decimate(hr).takeIf { it.size >= 2 },
            )
        }
        return days to acts
    }
}
