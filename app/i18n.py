"""Textos da interface e mensagens localizadas do Tuberino Downloader."""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_LANGUAGES = ("pt-BR", "en-US")

_TEXT: dict[str, dict[str, str]] = {
    "app_title": {"pt-BR": "Tuberino Downloader", "en-US": "Tuberino Downloader"},
    "youtube": {"pt-BR": "YouTube", "en-US": "YouTube"},
    "twitch": {"pt-BR": "Twitch", "en-US": "Twitch"},
    "twitter_x": {"pt-BR": "Twitter/X", "en-US": "Twitter/X"},
    "instagram": {"pt-BR": "Instagram", "en-US": "Instagram"},
    "video": {"pt-BR": "Vídeo", "en-US": "Video"},
    "playlist": {"pt-BR": "Playlist", "en-US": "Playlist"},
    "vod": {"pt-BR": "VOD", "en-US": "VOD"},
    "clip": {"pt-BR": "Clip", "en-US": "Clip"},
    "add_label": {"pt-BR": "Adicionar:", "en-US": "Add:"},
    "video_url_placeholder": {
        "pt-BR": "Cole o link de um vídeo do YouTube",
        "en-US": "Paste a YouTube video link",
    },
    "playlist_url_placeholder": {
        "pt-BR": "Cole o link de uma playlist do YouTube",
        "en-US": "Paste a YouTube playlist link",
    },
    "vod_url_placeholder": {
        "pt-BR": "Cole o link de um VOD da Twitch",
        "en-US": "Paste a Twitch VOD link",
    },
    "clip_url_placeholder": {
        "pt-BR": "Cole o link de um clip da Twitch",
        "en-US": "Paste a Twitch clip link",
    },
    "twitter_url_placeholder": {
        "pt-BR": "Cole o link de um vídeo do Twitter/X",
        "en-US": "Paste a Twitter/X video link",
    },
    "instagram_url_placeholder": {
        "pt-BR": "Cole o link de um vídeo, reel ou story do Instagram",
        "en-US": "Paste an Instagram video, reel or story link",
    },
    "choose_source_tooltip": {
        "pt-BR": "Escolha se a URL contém um vídeo ou uma playlist",
        "en-US": "Choose whether the URL contains a video or a playlist",
    },
    "add": {"pt-BR": "Adicionar", "en-US": "Add"},
    "analyze": {"pt-BR": "Analisar", "en-US": "Analyze"},
    "content": {"pt-BR": "Conteúdo", "en-US": "Content"},
    "no_content": {
        "pt-BR": "Nenhum conteúdo analisado",
        "en-US": "No content analyzed",
    },
    "activate_all": {"pt-BR": "Ativar todos", "en-US": "Select all"},
    "deactivate_all": {"pt-BR": "Desativar todos", "en-US": "Deselect all"},
    "clear_list": {"pt-BR": "Limpar lista", "en-US": "Clear list"},
    "output_options": {"pt-BR": "Opções de saída", "en-US": "Output options"},
    "type": {"pt-BR": "Tipo:", "en-US": "Type:"},
    "mp3": {"pt-BR": "MP3", "en-US": "MP3"},
    "quality": {"pt-BR": "Qualidade:", "en-US": "Quality:"},
    "best_quality": {"pt-BR": "Maior qualidade", "en-US": "Highest quality"},
    "worst_quality": {"pt-BR": "Menor qualidade", "en-US": "Lowest quality"},
    "container": {"pt-BR": "Container:", "en-US": "Container:"},
    "mp4_compatible": {
        "pt-BR": "MP4 compatível H.264",
        "en-US": "Compatible MP4 H.264",
    },
    "original_format": {"pt-BR": "Formato original", "en-US": "Original format"},
    "convert_mp4": {"pt-BR": "Converter para MP4", "en-US": "Convert to MP4"},
    "mp4_tooltip": {
        "pt-BR": "Converter para MP4 pode demorar e reduzir a qualidade.",
        "en-US": "Converting to MP4 may take time and reduce quality.",
    },
    "mp4_available": {
        "pt-BR": "Disponível para esta qualidade.",
        "en-US": "Available for this quality.",
    },
    "mp4_unavailable": {
        "pt-BR": "Indisponível: esta qualidade não tem combinação H.264 + AAC compatível.",
        "en-US": "Unavailable: this quality has no compatible H.264 + AAC combination.",
    },
    "quality_placeholder": {
        "pt-BR": "Analise um vídeo para listar qualidades",
        "en-US": "Analyze a video to list available qualities",
    },
    "video_available": {"pt-BR": "Vídeo disponível", "en-US": "Video available"},
    "unknown_format": {"pt-BR": "formato desconhecido", "en-US": "unknown format"},
    "thumbnail": {"pt-BR": "Miniatura", "en-US": "Thumbnail"},
    "thumbnails_disabled": {
        "pt-BR": "Miniaturas desativadas",
        "en-US": "Thumbnails disabled",
    },
    "open_original_tooltip": {
        "pt-BR": "Abrir vídeo original no navegador",
        "en-US": "Open the original video in the browser",
    },
    "include_item_tooltip": {
        "pt-BR": "Incluir este item no download",
        "en-US": "Include this item in the download",
    },
    "remove_item_tooltip": {
        "pt-BR": "Remover este item da lista",
        "en-US": "Remove this item from the list",
    },
    "channel_unavailable": {
        "pt-BR": "Canal indisponível",
        "en-US": "Channel unavailable",
    },
    "duration_unavailable": {
        "pt-BR": "Duração indisponível",
        "en-US": "Duration unavailable",
    },
    "completed": {"pt-BR": "Concluído", "en-US": "Completed"},
    "download_failed": {"pt-BR": "Falha no download", "en-US": "Download failed"},
    "cancelled": {"pt-BR": "Cancelado", "en-US": "Cancelled"},
    "downloading_label": {"pt-BR": "Baixando", "en-US": "Downloading"},
    "merging_label": {"pt-BR": "Mesclando", "en-US": "Merging"},
    "converting_label": {"pt-BR": "Convertendo", "en-US": "Converting"},
    "validating_label": {"pt-BR": "Validando", "en-US": "Validating"},
    "processing_label": {"pt-BR": "Processando", "en-US": "Processing"},
    "mp3_bitrate": {"pt-BR": "Bitrate MP3:", "en-US": "MP3 bitrate:"},
    "bitrate_tooltip": {
        "pt-BR": "Bitrate final de codificação; não melhora a fonte original.",
        "en-US": "Final encoding bitrate; it cannot improve the original source.",
    },
    "destination": {"pt-BR": "Destino:", "en-US": "Destination:"},
    "destination_tooltip": {
        "pt-BR": "Pasta em que o arquivo final será salvo",
        "en-US": "Folder where the final file will be saved",
    },
    "browse": {"pt-BR": "Procurar", "en-US": "Browse"},
    "open_folder": {"pt-BR": "Abrir pasta", "en-US": "Open folder"},
    "download": {"pt-BR": "Baixar", "en-US": "Download"},
    "cancel": {"pt-BR": "Cancelar", "en-US": "Cancel"},
    "ready": {"pt-BR": "Pronto", "en-US": "Ready"},
    "analyzing_content": {"pt-BR": "Analisando conteúdo...", "en-US": "Analyzing content..."},
    "ready_to_download": {
        "pt-BR": "Pronto para baixar",
        "en-US": "Ready to download",
    },
    "downloading": {"pt-BR": "Baixando...", "en-US": "Downloading..."},
    "converting": {"pt-BR": "Convertendo...", "en-US": "Converting..."},
    "validating": {"pt-BR": "Validando...", "en-US": "Validating..."},
    "processing": {"pt-BR": "Processando...", "en-US": "Processing..."},
    "analyzing_label": {"pt-BR": "Analisando", "en-US": "Analyzing"},
    "closing_tasks": {
        "pt-BR": "Encerrando tarefas em andamento...",
        "en-US": "Closing running tasks...",
    },
    "download_failed_generic": {
        "pt-BR": "Não foi possível concluir o download.",
        "en-US": "Could not complete the download.",
    },
    "file": {"pt-BR": "Arquivo", "en-US": "File"},
    "exit": {"pt-BR": "Sair", "en-US": "Exit"},
    "options": {"pt-BR": "Opções", "en-US": "Options"},
    "settings": {"pt-BR": "Configurações", "en-US": "Settings"},
    "dependencies": {"pt-BR": "Dependências", "en-US": "Dependencies"},
    "about": {"pt-BR": "Sobre", "en-US": "About"},
    "about_app": {
        "pt-BR": "Sobre o Tuberino Downloader",
        "en-US": "About Tuberino Downloader",
    },
    "check_updates": {
        "pt-BR": "Verificar atualizações",
        "en-US": "Check for updates",
    },
    "support": {"pt-BR": "Suporte", "en-US": "Support"},
    "support_tooltip": {
        "pt-BR": "Ajuda e suporte do projeto",
        "en-US": "Project help and support",
    },
    "settings_title": {"pt-BR": "Configurações", "en-US": "Settings"},
    "configuration": {"pt-BR": "Configuração", "en-US": "Configuration"},
    "language": {"pt-BR": "Idioma:", "en-US": "Language:"},
    "language_pt": {
        "pt-BR": "Português (Brasil)",
        "en-US": "Portuguese (Brazil)",
    },
    "language_en": {
        "pt-BR": "Inglês (Estados Unidos)",
        "en-US": "English (United States)",
    },
    "language_future": {
        "pt-BR": "Outros idiomas serão adicionados posteriormente.",
        "en-US": "More languages will be added later.",
    },
    "theme": {"pt-BR": "Tema:", "en-US": "Theme:"},
    "theme_night": {"pt-BR": "Noturno", "en-US": "Night"},
    "theme_day": {"pt-BR": "Claro", "en-US": "Day"},
    "always_on_top": {"pt-BR": "Sempre no topo", "en-US": "Always on top"},
    "check_updates_startup": {
        "pt-BR": "Verificar atualizações ao iniciar",
        "en-US": "Check for updates on startup",
    },
    "updater_future": {
        "pt-BR": "As atualizações são consultadas no GitHub Releases.",
        "en-US": "Updates are checked through GitHub Releases.",
    },
    "thumbnail_limit": {
        "pt-BR": "Limite de miniaturas em playlists:",
        "en-US": "Playlist thumbnail limit:",
    },
    "thumbnail_limit_tooltip": {
        "pt-BR": "Playlists com até este número de vídeos poderão carregar miniaturas.",
        "en-US": "Playlists up to this number of videos may load thumbnails.",
    },
    "videos_suffix": {"pt-BR": " vídeos", "en-US": " videos"},
    "default": {"pt-BR": "Padrão", "en-US": "Default"},
    "ok": {"pt-BR": "OK", "en-US": "OK"},
    "close": {"pt-BR": "Fechar", "en-US": "Close"},
    "remove_item": {"pt-BR": "Remover item", "en-US": "Remove item"},
    "remove_item_prompt": {
        "pt-BR": "Deseja remover este item da lista?\n\n{title}",
        "en-US": "Do you want to remove this item from the list?\n\n{title}",
    },
    "clear_list_title": {"pt-BR": "Limpar lista", "en-US": "Clear list"},
    "clear_list_prompt": {
        "pt-BR": "Deseja remover todos os itens da lista?",
        "en-US": "Do you want to remove all items from the list?",
    },
    "list_count_prompt": {
        "pt-BR": "A lista atual contém {count} {item_label}. Deseja continuar?",
        "en-US": "The current list contains {count} {item_label}. Do you want to continue?",
    },
    "switch_platform_prompt": {
        "pt-BR": "Trocar de plataforma limpará a lista atual.",
        "en-US": "Switching platforms will clear the current list.",
    },
    "switch_content_prompt": {
        "pt-BR": "Trocar o tipo de conteúdo limpará a lista atual.",
        "en-US": "Switching the content type will clear the current list.",
    },
    "replace_playlist_prompt": {
        "pt-BR": "Analisar uma nova playlist substituirá a lista atual.",
        "en-US": "Analyzing a new playlist will replace the current list.",
    },
    "close_title": {"pt-BR": "Tarefa em andamento", "en-US": "Task in progress"},
    "close_prompt": {
        "pt-BR": "Há uma tarefa em andamento. Deseja fechar a janela?",
        "en-US": "A task is still running. Do you want to close the window?",
    },
    "choose_destination": {
        "pt-BR": "Escolha a pasta de destino",
        "en-US": "Choose the destination folder",
    },
    "clear_progress": {"pt-BR": "Limpando lista", "en-US": "Clearing list"},
    "list_clearing": {"pt-BR": "Limpando lista...", "en-US": "Clearing list..."},
    "list_clearing_error": {
        "pt-BR": "Não foi possível limpar a lista.",
        "en-US": "Could not clear the list.",
    },
    "playlist_load_error": {
        "pt-BR": "Não foi possível carregar a lista da playlist.",
        "en-US": "Could not load the playlist list.",
    },
    "analysis_cancelled": {"pt-BR": "Análise cancelada.", "en-US": "Analysis cancelled."},
    "video_unavailable": {"pt-BR": "Vídeo não disponível.", "en-US": "Video unavailable."},
    "unavailable": {"pt-BR": "Não disponível", "en-US": "Unavailable"},
    "no_quality": {
        "pt-BR": "Nenhuma qualidade de vídeo compatível foi disponibilizada.",
        "en-US": "No compatible video quality was available.",
    },
    "unrecognized_content": {
        "pt-BR": "A análise não retornou conteúdo reconhecível.",
        "en-US": "The analysis did not return recognizable content.",
    },
    "invalid_video_url": {
        "pt-BR": "Cole um link válido de vídeo do YouTube.",
        "en-US": "Paste a valid YouTube video link.",
    },
    "invalid_playlist_url": {
        "pt-BR": "Cole um link válido de playlist do YouTube.",
        "en-US": "Paste a valid YouTube playlist link.",
    },
    "invalid_vod_url": {
        "pt-BR": "Cole um link válido de VOD da Twitch.",
        "en-US": "Paste a valid Twitch VOD link.",
    },
    "invalid_clip_url": {
        "pt-BR": "Cole um link válido de clip da Twitch.",
        "en-US": "Paste a valid Twitch clip link.",
    },
    "invalid_twitter_url": {
        "pt-BR": "Cole um link válido de vídeo do Twitter/X.",
        "en-US": "Paste a valid Twitter/X video link.",
    },
    "invalid_instagram_url": {
        "pt-BR": "Cole um link válido de vídeo do Instagram.",
        "en-US": "Paste a valid Instagram video link.",
    },
    "duplicate_video": {
        "pt-BR": "Este vídeo já está na lista.",
        "en-US": "This video is already in the list.",
    },
    "analyze_before_download": {
        "pt-BR": "Analise um vídeo ou uma playlist antes de baixar.",
        "en-US": "Analyze a video or playlist before downloading.",
    },
    "select_item_before_download": {
        "pt-BR": "Ative pelo menos um item para baixar.",
        "en-US": "Select at least one item to download.",
    },
    "dependencies_pending": {
        "pt-BR": "O diagnóstico de dependências ainda não terminou. Analise novamente.",
        "en-US": "The dependency check is not finished yet. Analyze again.",
    },
    "invalid_bitrate": {
        "pt-BR": "Escolha um bitrate MP3 válido.",
        "en-US": "Choose a valid MP3 bitrate.",
    },
    "invalid_playlist_quality": {
        "pt-BR": "Escolha uma qualidade de playlist válida.",
        "en-US": "Choose a valid playlist quality.",
    },
    "invalid_profile": {
        "pt-BR": "Escolha um perfil de saída válido.",
        "en-US": "Choose a valid output profile.",
    },
    "quality_unavailable": {
        "pt-BR": "Escolha uma qualidade de vídeo disponível.",
        "en-US": "Choose an available video quality.",
    },
    "video_info_before_download": {
        "pt-BR": "Analise um vídeo antes de baixar.",
        "en-US": "Analyze a video before downloading.",
    },
    "download_cancelled": {"pt-BR": "Download cancelado.", "en-US": "Download cancelled."},
    "partial_download": {
        "pt-BR": "Concluído parcialmente: {count} itens; alguns falharam.",
        "en-US": "Partially completed: {count} items; some failed.",
    },
    "completed_items": {"pt-BR": "Concluído: {count} itens", "en-US": "Completed: {count} items"},
    "completed_file": {"pt-BR": "Concluído: {name}", "en-US": "Completed: {name}"},
    "download_cancelling": {"pt-BR": "Cancelando...", "en-US": "Cancelling..."},
    "dependency_running": {
        "pt-BR": "A verificação ainda está em andamento. Tente novamente em instantes.",
        "en-US": "The check is still running. Try again in a moment.",
    },
    "dependency_diagnostic": {
        "pt-BR": "Diagnóstico de dependências",
        "en-US": "Dependency diagnostics",
    },
    "ready_status": {"pt-BR": "Pronto", "en-US": "Ready"},
    "path": {"pt-BR": "Caminho", "en-US": "Path"},
    "not_found": {"pt-BR": "não encontrado", "en-US": "not found"},
    "version_unavailable": {"pt-BR": "versão indisponível", "en-US": "version unavailable"},
    "about_text": {
        "pt-BR": "Tuberino Downloader\n\nDownloader de vídeos e MP3 do YouTube.\n"
        "Fase 1 — versão de desenvolvimento.",
        "en-US": "Tuberino Downloader\n\nYouTube video and MP3 downloader.\n"
        "Phase 1 — development version.",
    },
    "about_title": {
        "pt-BR": "Sobre — Tuberino Downloader",
        "en-US": "About — Tuberino Downloader",
    },
    "version_label": {"pt-BR": "Versão", "en-US": "Version"},
    "about_description": {
        "pt-BR": "Downloader de vídeos e áudio para YouTube, Twitch e Twitter/X.",
        "en-US": "Video and audio downloader for YouTube, Twitch and Twitter/X.",
    },
    "github_link": {"pt-BR": "GitHub", "en-US": "GitHub"},
    "support_project": {"pt-BR": "Apoie o projeto", "en-US": "Support the project"},
    "support_text": {
        "pt-BR": ("Para suporte, consulte o README.md e o arquivo logs/log.txt."),
        "en-US": "For support, check README.md and the logs/log.txt file.",
    },
    "update_repository_missing": {
        "pt-BR": (
            "A verificação de atualizações será conectada ao GitHub "
            "quando o repositório for configurado."
        ),
        "en-US": "Update checking will be connected to GitHub when the repository is configured.",
    },
    "update_dialog_title": {
        "pt-BR": "Verificar atualizações",
        "en-US": "Check for Updates",
    },
    "update_group": {"pt-BR": "Atualizações", "en-US": "Updates"},
    "update_checking": {
        "pt-BR": "Verificando o GitHub Releases...",
        "en-US": "Checking GitHub Releases...",
    },
    "update_no_update": {
        "pt-BR": "Você já está usando a versão mais recente.",
        "en-US": "You are already using the latest version.",
    },
    "update_available": {
        "pt-BR": "Uma nova versão está disponível.",
        "en-US": "A new version is available.",
    },
    "update_failed": {
        "pt-BR": "Não foi possível verificar ou preparar a atualização.",
        "en-US": "The update could not be checked or prepared.",
    },
    "update_current_version_label": {"pt-BR": "Versão atual", "en-US": "Current version"},
    "update_status_label": {"pt-BR": "Status", "en-US": "Status"},
    "update_latest_version_label": {"pt-BR": "Nova versão", "en-US": "Latest version"},
    "update_latest_version": {
        "pt-BR": "Nova versão: {version}",
        "en-US": "New version: {version}",
    },
    "update_changelog": {"pt-BR": "Notas da versão", "en-US": "Release notes"},
    "update_download_install": {
        "pt-BR": "Baixar e instalar",
        "en-US": "Download and install",
    },
    "update_downloading": {
        "pt-BR": "Baixando e validando a atualização...",
        "en-US": "Downloading and validating the update...",
    },
    "update_ready": {
        "pt-BR": "Atualização pronta para instalar.",
        "en-US": "Update ready to install.",
    },
    "update_install_title": {
        "pt-BR": "Instalar atualização",
        "en-US": "Install update",
    },
    "update_install_prompt": {
        "pt-BR": (
            "A atualização foi baixada e validada. O aplicativo será fechado e reiniciado "
            "para instalar a versão {version}. Continuar?"
        ),
        "en-US": (
            "The update was downloaded and verified. The application will close and restart "
            "to install version {version}. Continue?"
        ),
    },
    "update_active_task": {
        "pt-BR": "Finalize ou cancele a tarefa atual antes de instalar uma atualização.",
        "en-US": "Finish or cancel the current task before installing an update.",
    },
    "update_launch_failed": {
        "pt-BR": "Não foi possível iniciar o instalador auxiliar. O aplicativo continuará aberto.",
        "en-US": "The helper updater could not be started. The application will remain open.",
    },
    "update_preflight_failed": {
        "pt-BR": (
            "Não foi possível preparar a pasta do aplicativo para a atualização. "
            "O aplicativo continuará aberto."
        ),
        "en-US": (
            "The application folder could not be prepared for the update. "
            "The application will remain open."
        ),
    },
    "update_helper_missing": {
        "pt-BR": "O instalador auxiliar não foi encontrado. O aplicativo continuará aberto.",
        "en-US": "The helper updater was not found. The application will remain open.",
    },
    "item": {"pt-BR": "item", "en-US": "item"},
    "items": {"pt-BR": "itens", "en-US": "items"},
    "none": {"pt-BR": "nenhum", "en-US": "none"},
    "status_missing": {"pt-BR": "ausente", "en-US": "missing"},
    "status_invalid": {"pt-BR": "inválida", "en-US": "invalid"},
    "status_error": {"pt-BR": "erro", "en-US": "error"},
}

_MESSAGE_TRANSLATIONS = {
    "Não foi possível consultar o vídeo. Verifique sua conexão.": (
        "Could not retrieve the video. Check your connection."
    ),
    "Não foi possível consultar o conteúdo da Twitch. Verifique sua conexão.": (
        "Could not retrieve the Twitch content. Check your connection."
    ),
    "Não foi possível consultar a playlist. Verifique sua conexão.": (
        "Could not retrieve the playlist. Check your connection."
    ),
    "A resposta do YouTube não trouxe uma playlist válida.": (
        "The YouTube response did not contain a valid playlist."
    ),
    "A URL não retornou uma playlist do YouTube.": "The URL did not return a YouTube playlist.",
    "A resposta do YouTube não trouxe metadados válidos.": (
        "The YouTube response did not contain valid metadata."
    ),
    "Playlist e analise novamente.": "Playlist. Analyze again.",
    "O tipo de conteúdo da Twitch não é válido.": "The Twitch content type is invalid.",
    "URL de vídeo do YouTube válida.": "Valid YouTube video URL.",
    "URL de playlist do YouTube válida.": "Valid YouTube playlist URL.",
    "URL de VOD da Twitch válida.": "Valid Twitch VOD URL.",
    "URL de clip da Twitch válida.": "Valid Twitch clip URL.",
    "Cole um link válido de vídeo do YouTube, Twitch ou Twitter/X.": (
        "Paste a valid YouTube, Twitch, or Twitter/X video link."
    ),
    "URL de vídeo do Twitter/X válida.": "Valid Twitter/X video URL.",
    "Cole um link válido de vídeo do Twitter/X.": "Paste a valid Twitter/X video link.",
    "URL de vídeo do Instagram válida.": "Valid Instagram video URL.",
    "Cole um link válido de vídeo do Instagram.": "Paste a valid Instagram video link.",
    "Não foi possível consultar o vídeo do Instagram. Verifique sua conexão.": (
        "Could not retrieve the Instagram video. Check your connection."
    ),
    "Este conteúdo exige autenticação para ser acessado neste ambiente.": (
        "This content requires authentication to be accessed in this environment."
    ),
    "Não foi possível consultar o vídeo do Twitter/X. Verifique sua conexão.": (
        "Could not retrieve the Twitter/X video. Check your connection."
    ),
    "O arquivo final não foi encontrado após o download.": (
        "The final file was not found after the download."
    ),
    "O arquivo final está vazio.": "The final file is empty.",
    "A conversão não produziu um arquivo MP3.": "The conversion did not produce an MP3 file.",
    "FFprobe é necessário para validar o arquivo final.": (
        "FFprobe is required to validate the final file."
    ),
    "O arquivo final não contém vídeo e áudio válidos.": (
        "The final file does not contain valid video and audio."
    ),
    "O arquivo final MP3 não contém somente uma trilha de áudio válida.": (
        "The final MP3 does not contain only a valid audio track."
    ),
    "A validação do arquivo excedeu o tempo limite.": "File validation timed out.",
    "Não foi possível executar FFprobe.": "Could not run FFprobe.",
    "FFprobe rejeitou o arquivo final.": "FFprobe rejected the final file.",
    "FFprobe não encontrou trilhas de mídia.": "FFprobe did not find media streams.",
    "Arquivo final validado com sucesso.": "Final file validated successfully.",
    "Vídeo não disponível.": "Video unavailable.",
    "Não disponível": "Unavailable",
    "Download cancelado.": "Download cancelled.",
    "Falha no download.": "Download failed.",
    "Convertendo para MP4...": "Converting to MP4...",
    "Convertendo para MP3...": "Converting to MP3...",
    "Convertendo mídia...": "Converting media...",
    "Validando arquivo final...": "Validating final file...",
    "Não foi possível concluir o download.": "Could not complete the download.",
    "Não foi possível salvar na pasta escolhida.": "Could not save to the selected folder.",
    "Não foi possível salvar na pasta escolhida: verifique o espaço livre.": (
        "Could not save to the selected folder: check available space."
    ),
    "Não foi possível concluir o download. Verifique sua conexão.": (
        "Could not complete the download. Check your connection."
    ),
    "FFmpeg e FFprobe são necessários para unir/converter mídia.": (
        "FFmpeg and FFprobe are required to merge or convert media."
    ),
    "Não foi possível localizar a mídia para conversão MP4.": (
        "Could not locate media for MP4 conversion."
    ),
    "O FFmpeg disponível não oferece um codificador H.264 para MP4.": (
        "The available FFmpeg does not provide an H.264 encoder for MP4."
    ),
    "Não foi possível iniciar a conversão para MP4.": "Could not start MP4 conversion.",
    "A conversão para MP4 excedeu o tempo esperado.": "MP4 conversion exceeded the expected time.",
    "A conversão para MP4 falhou após a transferência.": (
        "MP4 conversion failed after the download."
    ),
    "Não foi possível concluir este item.": "Could not complete this item.",
    "Falha no item.": "Item failed.",
    "Item cancelado.": "Item cancelled.",
    "Dependência pronta.": "Dependency ready.",
    "A verificação excedeu o tempo limite.": "The check timed out.",
    "O executável retornou erro ao informar a versão.": (
        "The executable returned an error while reporting its version."
    ),
    "O destino escolhido não é uma pasta.": "The selected destination is not a folder.",
    "A pasta de destino não existe.": "The destination folder does not exist.",
    "Não foi possível criar a pasta de destino.": "Could not create the destination folder.",
    "Não foi possível gravar na pasta escolhida.": "Could not write to the selected folder.",
    "O tamanho estimado não pode ser negativo.": "The estimated size cannot be negative.",
    "Não foi possível verificar o espaço disponível.": ("Could not check the available space."),
    "Não há espaço livre suficiente na pasta escolhida.": (
        "There is not enough free space in the selected folder."
    ),
    "Já existe um arquivo com esse nome no destino.": (
        "A file with that name already exists in the destination."
    ),
    "A qualidade escolhida não contém vídeo.": "The selected quality has no video.",
    "A qualidade escolhida não tem áudio compatível disponível.": (
        "The selected quality has no compatible audio available."
    ),
    "Não há faixa de áudio disponível para esta qualidade.": (
        "No audio track is available for this quality."
    ),
    "Perfil de saída desconhecido.": "Unknown output profile.",
    "O bitrate MP3 deve ser 128, 192 ou 320 kbps.": ("MP3 bitrate must be 128, 192, or 320 kbps."),
    "FFmpeg e FFprobe são necessários para converter mídia.": (
        "FFmpeg and FFprobe are required to convert media."
    ),
    "Nenhuma faixa de áudio compatível foi disponibilizada.": (
        "No compatible audio track was available."
    ),
    "Playlists oferecem apenas Formato original ou Converter para MP4.": (
        "Playlists only offer Original format or Convert to MP4."
    ),
    "No modo Vídeo, selecione uma URL de vídeo em vez de uma playlist.": (
        "In Video mode, choose a video URL instead of a playlist."
    ),
    "A resposta de FFprobe não é válida.": "The FFprobe response is invalid.",
    "Streams lidos.": "Streams read.",
    "A Twitch recusou este download nesta sessão. Analise novamente e tente outra qualidade.": (
        "Twitch rejected this download in this session. Analyze again and try another quality."
    ),
    (
        "O YouTube restringiu este download nesta sessão. Atualize dependências ou tente outro "
        "vídeo autorizado."
    ): (
        "YouTube restricted this download in this session. Update dependencies or try another "
        "authorized video."
    ),
    "Nenhum vídeo disponível foi encontrado na playlist.": (
        "No available video was found in the playlist."
    ),
    (
        "A análise retornou uma playlist no modo de vídeo; selecione uma URL de playlist e "
        "analise novamente."
    ): ("The analysis returned a playlist in Video mode; choose a playlist URL and analyze again."),
    "Nenhum formato compatível foi disponibilizado para este vídeo.": (
        "No compatible format was available for this video."
    ),
    "Este vídeo não está disponível para download neste ambiente.": (
        "This video is not available for download in this environment."
    ),
    (
        "A qualidade escolhida não tem combinação MP4 compatível. Analise novamente ou "
        "escolha outra qualidade."
    ): (
        "The selected quality has no compatible MP4 combination. Analyze again or choose "
        "another quality."
    ),
    (
        "A qualidade escolhida não tem vídeo H.264 compatível com MP4. Analise novamente "
        "ou escolha outra qualidade."
    ): (
        "The selected quality has no H.264 video compatible with MP4. Analyze again or "
        "choose another quality."
    ),
    (
        "Não há áudio AAC/M4A compatível para esta qualidade no perfil MP4. Analise "
        "novamente ou escolha outra qualidade."
    ): (
        "There is no AAC/M4A audio compatible with this quality in the MP4 profile. "
        "Analyze again or choose another quality."
    ),
    "Não há faixa de áudio disponível para converter esta qualidade.": (
        "No audio track is available to convert this quality."
    ),
    "A qualidade escolhida não está mais disponível. Analise novamente.": (
        "The selected quality is no longer available. Analyze again."
    ),
    "Transferência concluída; aguardando validação do arquivo final.": (
        "Transfer complete; waiting to validate the final file."
    ),
    "Baixando mídia...": "Downloading media...",
    "Atualize o Deno para uma versão compatível (mínimo 2.3.0).": (
        "Update Deno to a compatible version (2.3.0 or newer)."
    ),
}


@dataclass(frozen=True, slots=True)
class Translator:
    """Tradutor leve para textos da UI e mensagens recebidas dos serviços."""

    language: str = "en-US"

    def __post_init__(self) -> None:
        if self.language not in SUPPORTED_LANGUAGES:
            object.__setattr__(self, "language", "en-US")

    def text(self, key: str, **values: object) -> str:
        template = _TEXT.get(key, {}).get(self.language) or _TEXT.get(key, {}).get("pt-BR", key)
        return template.format(**values) if values else template

    def message(self, value: str) -> str:
        if self.language == "en-US":
            translated = _MESSAGE_TRANSLATIONS.get(value)
            if translated is not None:
                return translated
            if value.startswith("Instale ") and " ou execute scripts/setup_tools.ps1." in value:
                dependency = value.removeprefix("Instale ").removesuffix(
                    " ou execute scripts/setup_tools.ps1."
                )
                return f"Install {dependency} or run scripts/setup_tools.ps1."
            if value.startswith("O caminho configurado para ") and value.endswith(
                " não é um executável válido."
            ):
                dependency = value.removeprefix("O caminho configurado para ").removesuffix(
                    " não é um executável válido."
                )
                return f"The configured path for {dependency} is not a valid executable."
            if value.startswith("Não foi possível executar ") and value.endswith("."):
                dependency = value.removeprefix("Não foi possível executar ").removesuffix(".")
                return f"Could not run {dependency}."
            if value.startswith("Instale ou atualize o pacote Python ") and value.endswith("."):
                package = value.removeprefix("Instale ou atualize o pacote Python ").removesuffix(
                    "."
                )
                return f"Install or update the Python package {package}."
            if value.startswith("Falha ao executar a dependência:"):
                return "Dependency execution failed."
            if value == "Pacote Python encontrado.":
                return "Python package found."
            if value == "O pacote Python não foi encontrado.":
                return "The Python package was not found."
            if value == "Atualize o Deno para uma versão compatível.":
                return "Update Deno to a compatible version."
            return value
        for portuguese, english in _MESSAGE_TRANSLATIONS.items():
            if value == english:
                return portuguese
        for localized in _TEXT.values():
            if value == localized.get("en-US"):
                return localized.get("pt-BR", value)
        return value

    def content_count(self, selected: int, total: int) -> str:
        label = self.text("item" if total == 1 else "items")
        if self.language == "en-US" and total == 1:
            label = "item"
        return f"{selected} / {total} {label.capitalize() if self.language == 'pt-BR' else label}"

    def dependency_status(self, value: str) -> str:
        key = {
            "missing": "status_missing",
            "invalid": "status_invalid",
            "error": "status_error",
        }.get(value)
        return self.text(key) if key else value
