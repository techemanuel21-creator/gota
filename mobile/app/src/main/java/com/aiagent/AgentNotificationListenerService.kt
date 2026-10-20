package com.aiagent

import android.service.notification.NotificationListenerService

class AgentNotificationListenerService : NotificationListenerService() {

    override fun onListenerConnected() {
        super.onListenerConnected()
        instance = this
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        instance = null
    }

    fun countUnreadFor(packageName: String): Int {
        return try {
            activeNotifications.count { it.packageName == packageName }
        } catch (e: Exception) {
            -1
        }
    }

    companion object {
        @Volatile
        var instance: AgentNotificationListenerService? = null
            private set

        fun isRunning(): Boolean = instance != null
    }
}
