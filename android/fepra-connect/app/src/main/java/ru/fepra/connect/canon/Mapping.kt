package ru.fepra.connect.canon

data class StageIv(val startSec: Long, val endSec: Long, val kind: String)

data class SleepAgg(val hours: Double, val deepH: Double?, val remH: Double?)

object Mapping {
    const val T_RUNNING = 56
    const val T_RUNNING_TREADMILL = 57
    const val T_BIKING = 8
    const val T_BIKING_STATIONARY = 9
    const val T_SWIMMING_OPEN_WATER = 73
    const val T_SWIMMING_POOL = 74

    fun sport(exerciseType: Int): String = when (exerciseType) {
        T_RUNNING, T_RUNNING_TREADMILL -> "run"
        T_BIKING, T_BIKING_STATIONARY -> "bike"
        T_SWIMMING_POOL, T_SWIMMING_OPEN_WATER -> "swim"
        else -> "other"
    }

    fun sleep(stages: List<StageIv>, sessionSec: Long): SleepAgg {
        if (stages.isEmpty()) return SleepAgg(round1(sessionSec / 3600.0), null, null)
        var asleep = 0L
        var deep = 0L
        var rem = 0L
        for (s in stages) {
            val dur = s.endSec - s.startSec
            when (s.kind) {
                "light", "sleep" -> asleep += dur
                "deep" -> { asleep += dur; deep += dur }
                "rem" -> { asleep += dur; rem += dur }
            }
        }
        return SleepAgg(
            round1(asleep / 3600.0),
            if (deep > 0) round1(deep / 3600.0) else null,
            if (rem > 0) round1(rem / 3600.0) else null,
        )
    }

    fun decimate(series: List<LongArray>, cap: Int = 1600): List<LongArray> {
        if (series.size <= cap) return series
        val step = (series.size + cap - 1) / cap
        return series.filterIndexed { i, _ -> i % step == 0 }
    }

    fun paceSecPerKm(durationSec: Long, distanceKm: Double?): Double? {
        if (distanceKm == null || distanceKm <= 0.0) return null
        return round1(durationSec / distanceKm)
    }

    fun round1(x: Double): Double = kotlin.math.round(x * 10.0) / 10.0
}
