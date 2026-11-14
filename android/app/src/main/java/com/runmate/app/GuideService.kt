package com.runmate.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

/**
 * 안내하는 동안 띄워 두는 포그라운드 서비스 (알림창에 "길안내 중").
 *
 * 달리다 화면을 잠그면 안드로이드는 백그라운드 앱의 위치를 한 시간에 몇 번으로 줄인다 — 그러면 안내가 멈춘다.
 * 위치를 쓰는 포그라운드 서비스가 떠 있으면 앱이 계속 '앞에서 도는' 것으로 쳐서, 잠가도 GPS와 음성 안내가 이어진다.
 * 안내 자체(위치 받기·음성)는 MainActivity가 그대로 한다. 이 서비스는 그동안 앱을 깨어 있게 할 뿐이다.
 */
class GuideService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = notification(intent?.getStringExtra(EXTRA_TEXT) ?: getString(R.string.guide_running))
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
        return START_NOT_STICKY   // 앱이 꺼지면 안내도 끝난 것이다 — 혼자 다시 살아나지 않는다
    }

    private fun notification(text: String): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL, getString(R.string.guide_channel), NotificationManager.IMPORTANCE_LOW)
            )
        }
        // 알림을 누르면 안내 화면으로 돌아간다
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(open)
            .build()
    }

    companion object {
        private const val CHANNEL = "guide"
        private const val NOTIFICATION_ID = 1
        private const val EXTRA_TEXT = "text"

        fun start(context: Context, text: String? = null) {
            val intent = Intent(context, GuideService::class.java).putExtra(EXTRA_TEXT, text)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(intent) else context.startService(intent)
        }

        /** 알림 문구만 바꾼다 (남은 거리 등). 서비스가 이미 떠 있으면 같은 알림을 고친다. */
        fun update(context: Context, text: String) = start(context, text)

        fun stop(context: Context) {
            context.stopService(Intent(context, GuideService::class.java))
        }
    }
}
