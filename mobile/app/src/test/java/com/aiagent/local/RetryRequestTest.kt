package com.aiagent.local

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RetryRequestTest {

    @Test
    fun asksForAnotherPicture() {
        listOf(
            "outra", "outra imagem", "de novo", "novamente", "mais uma", "mais uma vez", "gera outra",
            "gera outra imagem", "faz outra", "faz de novo", "tenta de novo", "desenha outra", "refaz",
            "refaz a imagem", "outra versao", "cria outra imagem"
        ).forEach { assertTrue("should retry: $it", AgentLoop.isRetryRequest(it)) }
    }

    @Test
    fun otherSentencesAreNotRetries() {
        listOf(
            "outra coisa", "fala de novo o clima de hoje", "nova conversa", "me explica de novo como funciona",
            "gera uma imagem de um gato", "quero outra pizza", "abre o whatsapp de novo por favor"
        ).forEach { assertFalse("should not retry: $it", AgentLoop.isRetryRequest(it)) }
    }
}
