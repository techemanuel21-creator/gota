package com.aiagent

import android.content.Intent
import android.os.Build
import android.provider.Settings
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import android.widget.Toast
import androidx.annotation.RequiresApi

/**
 * A "Gota" button in the Quick Settings panel (the shade you pull down from the top). Tapping it
 * summons Gota from any app, with no special permission — the universal way to call him, on any
 * phone, as a backup to the edge swipe.
 */
@RequiresApi(Build.VERSION_CODES.N)
class GotaTileService : TileService() {

    override fun onStartListening() {
        qsTile?.apply {
            state = Tile.STATE_INACTIVE
            label = "Gota"
            updateTile()
        }
    }

    override fun onClick() {
        super.onClick()
        if (!Settings.canDrawOverlays(this) || !VoiceService.running) {
            // Can't float the cat yet (overlay off or voice not enabled): send them to the app.
            val open = Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                startActivityAndCollapse(pendingOpen(open))
            } else {
                @Suppress("DEPRECATION")
                startActivityAndCollapse(open)
            }
            if (!VoiceService.running) Toast.makeText(this, "Ligue a chave \"Voz\" no Gota primeiro.", Toast.LENGTH_LONG).show()
            return
        }
        VoiceService.instance?.summon()
    }

    private fun pendingOpen(intent: Intent) = android.app.PendingIntent.getActivity(
        this, 0, intent, android.app.PendingIntent.FLAG_IMMUTABLE or android.app.PendingIntent.FLAG_UPDATE_CURRENT
    )
}
