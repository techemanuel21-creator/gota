package com.aiagent

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.Gravity
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.aiagent.local.AppCatalog
import com.aiagent.local.AppEntry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Lets the owner give nicknames to apps ("whats 2"), which Gota checks first when opening apps. */
class AppAliasesActivity : AppCompatActivity() {

    private lateinit var list: LinearLayout
    private var apps: List<AppEntry> = emptyList()
    private var filter = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(color(R.color.bg_dark))
            setPadding(dp(16), dp(28), dp(16), dp(8))
        }
        root.addView(TextView(this).apply {
            text = "Apelidos de apps"
            textSize = 22f
            setTextColor(color(R.color.text_primary))
        })
        root.addView(TextView(this).apply {
            text = "Toque em um app para dar um apelido. Depois é só pedir \"abrir <apelido>\" que o Gota entende. " +
                "Apps marcados com (2º) são a segunda cópia (ex.: o segundo WhatsApp)."
            textSize = 13f
            setTextColor(color(R.color.text_secondary))
            setPadding(0, dp(6), 0, dp(10))
        })
        val search = EditText(this).apply {
            hint = "Procurar app..."
            setBackgroundResource(R.drawable.bg_input)
            setPadding(dp(16), dp(12), dp(16), dp(12))
            setTextColor(color(R.color.text_primary))
            setHintTextColor(color(R.color.text_secondary))
            addTextChangedListener(object : TextWatcher {
                override fun afterTextChanged(s: Editable?) {
                    filter = AppCatalog.normalize(s?.toString().orEmpty())
                    render()
                }
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            })
        }
        root.addView(search)
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(ScrollView(this).apply { addView(list) }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)

        lifecycleScope.launch {
            apps = withContext(Dispatchers.IO) { AppCatalog.all(this@AppAliasesActivity) }
            render()
        }
    }

    private fun render() {
        list.removeAllViews()
        val aliases = AppCatalog.aliases(this)
        val visible = apps.filter { filter.isBlank() || AppCatalog.normalize(it.displayLabel).contains(filter) }
            .sortedBy { app -> if (aliases.containsValue(app.key)) 0 else 1 }
        visible.forEach { app ->
            val alias = aliases.entries.firstOrNull { it.value == app.key }?.key
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(4), dp(10), dp(4), dp(10))
                setOnClickListener { editAlias(app, alias) }
            }
            row.addView(ImageView(this).apply { setImageDrawable(AppCatalog.icon(this@AppAliasesActivity, app)) },
                LinearLayout.LayoutParams(dp(40), dp(40)))
            val texts = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(12), 0, 0, 0)
            }
            texts.addView(TextView(this).apply {
                text = app.displayLabel
                textSize = 15f
                setTextColor(color(R.color.text_primary))
            })
            texts.addView(TextView(this).apply {
                text = alias?.let { "Apelido: \"$it\"" } ?: "Sem apelido"
                textSize = 12f
                setTextColor(color(if (alias != null) R.color.accent else R.color.text_secondary))
            })
            row.addView(texts)
            list.addView(row)
        }
    }

    private fun editAlias(app: AppEntry, current: String?) {
        val input = EditText(this).apply {
            setText(current.orEmpty())
            hint = "ex.: whats 2"
            setPadding(dp(20), dp(16), dp(20), dp(16))
        }
        AlertDialog.Builder(this)
            .setTitle("Apelido para ${app.displayLabel}")
            .setView(input)
            .setPositiveButton("Salvar") { _, _ ->
                AppCatalog.setAlias(this, app, input.text.toString())
                render()
            }
            .setNeutralButton("Remover") { _, _ ->
                AppCatalog.setAlias(this, app, "")
                render()
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun color(id: Int) = ContextCompat.getColor(this, id)
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
