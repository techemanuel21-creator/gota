# Modelos de IA do Gota Desktop

Esta pasta guarda os modelos para o programa **não baixar nada no primeiro uso**. Ela não vai para o git (são ~5 GB).

| Pasta / arquivo | O que é | Licença |
|---|---|---|
| `gemma4_e2b.litertlm` (2,5 GB) | Gemma 4 E2B, o cérebro (conversa, visão da tela) | Gemma |
| `imagegen\sdxs_cpu.pte` (1,7 GB), `vocab.json`, `merges.txt` | pintor de imagens SDXS-512 DreamShaper | — |
| `imagegen\vae_decoder_fp32.pte` (190 MB) | decodificador completo (melhor qualidade) | — |
| `piper\` (60 MB) | voz masculina pt-BR "faber" (Piper) | MIT |
| `piper\en_US-joe-medium.onnx` (60 MB) | voz inglesa nativa (Piper "joe") para ler frases em inglês; ajustada ao tom da faber | CC0 |
| `vosk-pt\` (50 MB) | reconhecimento de fala que detecta quando você para de falar | Apache 2.0 |
| `whisper\` (460 MB) | Whisper small: transcrição precisa do que você diz | MIT |

Se algum arquivo faltar, o programa baixa só ele (resumível). Para usar outra pasta: variável de ambiente `GOTA_MODELS`.
