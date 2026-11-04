# Ferramentas locais

Esta pasta é reservada a ferramentas auxiliares usadas pelo aplicativo em
desenvolvimento. Os executáveis e arquivos compactados são ignorados pelo Git.

## Provisionamento explícito

Em um PowerShell aberto na raiz do projeto, execute conscientemente:

```powershell
.\scripts\setup_tools.ps1
```

O script baixa somente versões x64 do Windows a partir dos projetos oficiais,
confere o SHA-256 publicado e valida `ffmpeg --version`, `ffprobe --version` e
`deno --version`. Ele não é chamado pela inicialização do aplicativo. Para
substituir uma instalação local existente, use `-Force` depois de confirmar o
alvo:

```powershell
.\scripts\setup_tools.ps1 -Force
```

Destinos esperados:

```text
vendor/ffmpeg/bin/ffmpeg.exe
vendor/ffmpeg/bin/ffprobe.exe
vendor/deno/deno.exe
```

## Fontes e licenças

- FFmpeg: build x86_64 LGPL estática do [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), release `autobuild-2026-10-25-13-00`, asset `ffmpeg-N-128094-g31855b2a70-win64-lgpl.zip`. O build é uma distribuição do FFmpeg; a licença aplicável deve ser conferida nos arquivos distribuídos antes de qualquer futura distribuição do aplicativo.
- Deno: asset oficial `deno-x86_64-pc-windows-msvc.zip` da release `v2.9.8` do [denoland/deno](https://github.com/denoland/deno). O yt-dlp exige atualmente Deno >= 2.3.0 para o suporte EJS documentado.

O projeto não versiona esses binários. A versão efetivamente instalada deve ser
registrada em `docs/progress.md`. Se uma URL ou checksum deixar de existir, o
script falha sem executar o arquivo e a atualização do manifesto deve ser feita
manualmente após consultar a fonte oficial.

## Alternativa manual

Também é possível instalar FFmpeg/FFprobe e Deno por fontes oficiais, validar
as versões no terminal e colocar os executáveis nos caminhos acima, ou deixá-los
no `PATH`. O pacote Python `ffmpeg`/`ffmpeg-python` não substitui os executáveis
`ffmpeg.exe` e `ffprobe.exe`.

