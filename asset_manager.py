#!/usr/bin/env python3
"""
Asset Manager for DAKOSYS
Handles copying default assets (images, fonts) to the correct locations
"""

import os
import shutil
import logging
import yaml
import requests
from rich.console import Console
from shared_utils import setup_rotating_logger

__all__ = ['setup_assets', 'sync_anime_episode_collections', 'create_anime_overlay_files', 'update_anime_episode_collections']

console = Console()

if os.environ.get('RUNNING_IN_DOCKER') == 'true':
    data_dir = "/app/data"
else:
    data_dir = "data"  

log_file = os.path.join(data_dir, "anime_trakt_manager.log")
logger = setup_rotating_logger("anime_trakt_manager", log_file)

CONTAINER_ASSETS_DIR = "/app/assets"
CONTAINER_FONTS_DIR = "/app/fonts"

def ensure_directory(directory):
    """Ensure a directory exists, creating it if necessary."""
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            logger.info(f"Created directory: {directory}")
            return True
        except Exception as e:
            logger.error(f"Error creating directory {directory}: {str(e)}")
            return False
    return True

def get_kometa_paths(config):
    """Get overlay and collections paths from config, with fallbacks for backward compatibility."""
    yaml_output_dir = config.get('kometa_config', {}).get('yaml_output_dir')
    collections_dir = config.get('kometa_config', {}).get('collections_dir')

    if not yaml_output_dir and 'services' in config and 'tv_status_tracker' in config['services']:
        yaml_output_dir = config['services']['tv_status_tracker'].get('yaml_output_dir')

    if not collections_dir and 'services' in config and 'tv_status_tracker' in config['services']:
        collections_dir = config['services']['tv_status_tracker'].get('collections_dir')

    if not yaml_output_dir:
        yaml_output_dir = '/kometa/config/overlays'

    if not collections_dir:
        collections_dir = '/kometa/config/collections'

    return yaml_output_dir, collections_dir

def copy_asset(source, destination):
    """Copy an asset file, creating destination directory if needed."""
    try:
        dest_dir = os.path.dirname(destination)
        if not ensure_directory(dest_dir):
            return False

        shutil.copy2(source, destination)
        logger.info(f"Copied asset: {source} -> {destination}")
        return True
    except Exception as e:
        logger.error(f"Error copying asset {source} to {destination}: {str(e)}")
        return False

def setup_collection_posters(config):
    """Setup collection poster images."""
    _, collections_dir = get_kometa_paths(config)

    kometa_config = os.path.dirname(collections_dir)

    assets_dir = os.path.join(kometa_config, "assets", "Next Airing")
    if not ensure_directory(assets_dir):
        return False

    poster_source = os.path.join(CONTAINER_ASSETS_DIR, "next_airing_poster.jpg")
    poster_dest = os.path.join(assets_dir, "poster.jpg")

    if os.path.exists(poster_source):
        return copy_asset(poster_source, poster_dest)
    else:
        logger.warning(f"Poster image not found in container: {poster_source}")
        return False

def setup_fonts(config):
    """Setup fonts for TV Status Tracker."""
    kometa_config = "/kometa/config"
    if 'services' in config and 'tv_status_tracker' in config['services']:
        collections_dir = config['services']['tv_status_tracker'].get('collections_dir', '/kometa/config/collections')
        kometa_config = os.path.dirname(collections_dir)

    font_directory_name = config.get('kometa_config', {}).get('font_directory', 'config/fonts')
    fonts_dir = os.path.join(kometa_config, font_directory_name) 
    if not ensure_directory(fonts_dir):
        return False

    default_font_filename = "Juventus-Fans-Bold.ttf"
    font_source = os.path.join(CONTAINER_FONTS_DIR, default_font_filename)
    font_dest = os.path.join(fonts_dir, default_font_filename)

    if os.path.exists(font_source):
        if copy_asset(font_source, font_dest):
            logger.info(f"Default font '{default_font_filename}' ensured at {font_dest}")
            return True
    else:
        logger.warning(f"Default font not found in container: {font_source}")

    return False

def sync_anime_episode_collections(config, force_update=False):
    """
    Generate Kometa anime episode-type collections using Plex aired-order
    numbering instead of Trakt's season/episode numbering.

    Trakt list names are still used to determine which Dakosys anime/type
    combinations currently exist.
    """
    logger = logging.getLogger("asset_manager")

    yaml_output_dir, collections_dir = get_kometa_paths(config)

    if not ensure_directory(collections_dir):
        return False

    trakt_username = config.get('trakt', {}).get('username')
    if not trakt_username:
        logger.error(
            "Trakt username not found in config - "
            "cannot discover Dakosys episode lists"
        )
        return False

    import trakt_auth

    access_token = trakt_auth.ensure_trakt_auth(quiet=True)
    if not access_token:
        logger.error("Failed to get Trakt access token")
        return False

    headers = trakt_auth.get_trakt_headers(access_token)

    trakt_api_url = 'https://api.trakt.tv'
    lists_url = f"{trakt_api_url}/users/me/lists"

    response = requests.get(
        lists_url,
        headers=headers,
        params={"limit": 1000},
    )

    if response.status_code != 200:
        logger.error(
            f"Failed to get Trakt lists. "
            f"Status: {response.status_code}"
        )
        return False

    trakt_lists = response.json()

    anime_specs = []

    for trakt_list in trakt_lists:
        name = trakt_list.get('name', '')

        if '_' not in name:
            continue

        anime_name, episode_type = name.split('_', 1)
        normalized_type = episode_type.lower().strip()

        if normalized_type == 'filler':
            mapped_type = 'filler'

        elif normalized_type in (
            'manga-canon',
            'manga canon',
        ):
            mapped_type = 'manga'

        elif normalized_type in (
            'anime-canon',
            'anime canon',
        ):
            mapped_type = 'anime'

        elif normalized_type in (
            'mixed-canon-filler',
            'mixed canon/filler',
        ):
            mapped_type = 'mixed'

        else:
            continue

        anime_specs.append({
            'anime_name': anime_name,
            'episode_type': mapped_type,
        })

    if not anime_specs:
        logger.error(
            "No Dakosys anime episode lists found on Trakt"
        )
        return False

    episode_lists_dir = os.path.join(
        collections_dir,
        'anime_episode_lists',
    )

    try:
        from kometa_episode_mapper import (
            generate_kometa_episode_files,
        )

        success, stats = generate_kometa_episode_files(
            config,
            anime_specs,
            episode_lists_dir,
        )

        if not success:
            logger.error(
                "Failed generating Plex-aware Kometa episode files"
            )
            return False

    except Exception as e:
        logger.error(
            f"Error generating Kometa episode files: {str(e)}"
        )
        return False

    logger.info(
        "Plex-aware episode mapping complete: "
        f"{stats['shows_processed']} shows, "
        f"{stats['episodes_mapped']} episodes mapped, "
        f"{stats['episodes_unmapped']} unmapped, "
        f"{stats['title_warnings']} title warnings"
    )

    #
    # Work out how Kometa should reference the generated directory.
    #
    # Typical Dakosys path:
    #
    #   /kometa/config/collections/anime_episode_lists
    #
    # Kometa should receive:
    #
    #   config/collections/anime_episode_lists/...
    #
    normalized_dir = collections_dir.replace('\\', '/')

    config_marker = '/config/'
    kometa_marker = '/kometa/'

    if config_marker in normalized_dir:
        relative_collections_dir = normalized_dir.split(
            config_marker,
            1
        )[1]

        kometa_episode_dir = (
            f"config/{relative_collections_dir}/"
            f"anime_episode_lists"
        )
    elif normalized_dir.startswith(kometa_marker):
        relative_collections_dir = normalized_dir.split(
            kometa_marker,
            1
        )[1]

        kometa_episode_dir = (
            f"config/{relative_collections_dir}/"
            f"anime_episode_lists"
        )
    else:
        logger.warning(
            f"Could not derive Kometa-relative path from "
            f"{collections_dir}; using default config/collections"
        )

        kometa_episode_dir = (
            "config/collections/anime_episode_lists"
        )

    collections_data = {
        'collections': {
            'Fillers': {
                'text_file': (
                    f"{kometa_episode_dir}/filler.txt"
                ),
                'sync_mode': 'sync',
                'item_label': 'Fillers',
                'builder_level': 'episode',
                'cache_builders': 6,
            },

            'Manga Canon': {
                'text_file': (
                    f"{kometa_episode_dir}/manga_canon.txt"
                ),
                'sync_mode': 'sync',
                'item_label': 'MangaCanon',
                'builder_level': 'episode',
                'cache_builders': 6,
            },

            'Anime Canon': {
                'text_file': (
                    f"{kometa_episode_dir}/anime_canon.txt"
                ),
                'sync_mode': 'sync',
                'item_label': 'AnimeCanon',
                'builder_level': 'episode',
                'cache_builders': 6,
            },

            'Mixed Canon/Filler': {
                'text_file': (
                    f"{kometa_episode_dir}/mixed.txt"
                ),
                'sync_mode': 'sync',
                'item_label': 'Mixed',
                'builder_level': 'episode',
                'cache_builders': 6,
            },
        }
    }

    collections_file = os.path.join(
        collections_dir,
        'anime_episode_type.yml',
    )

    try:
        with open(
            collections_file,
            'w',
            encoding='utf-8',
        ) as file:
            yaml.dump(
                collections_data,
                file,
                default_flow_style=False,
                sort_keys=False,
            )

        logger.info(
            f"Wrote Plex-aware anime episode collections to "
            f"{collections_file}"
        )

        create_anime_overlay_files(config)

        return True

    except Exception as e:
        logger.error(
            f"Error writing collections file: {str(e)}"
        )
        return False

def create_anime_overlay_files(config):
    """Create the overlay files for anime episode types."""
    yaml_output_dir, _ = get_kometa_paths(config)
    logger = logging.getLogger("asset_manager")
    overlay_settings = config.get('services', {}).get('anime_episode_type', {}).get('overlay', {})

    if not ensure_directory(yaml_output_dir):
        return False

    font_path = "config/fonts/Juventus-Fans-Bold.ttf"

    overlay_configs = {
        'fillers.yml': {
            'overlay_name': 'filler_overlay',
            'name': 'Filler',
            'label': 'Filler'
        },
        'manga_canon.yml': {
            'overlay_name': 'manga_overlay',
            'name': 'Manga Canon',
            'label': 'MangaCanon'
        },
        'anime_canon.yml': {
            'overlay_name': 'anime_overlay',
            'name': 'Anime Canon',
            'label': 'AnimeCanon'
        },
        'mixed.yml': {
            'overlay_name': 'mixed_overlay',
            'name': 'Mixed Canon/Filler',
            'label': 'Mixed'
        }
    }

    success = True
    for filename, values in overlay_configs.items():
        overlay_file = os.path.join(yaml_output_dir, filename)
        
        if os.path.exists(overlay_file):
            continue
            
        overlay_content = {
            'overlays': {
                values['overlay_name']: {  
                    'builder_level': 'episode',
                    'overlay': {
                        'name': f"text({values['name']})",
                        'horizontal_offset': overlay_settings.get('horizontal_offset', 0),
                        'horizontal_align': overlay_settings.get('horizontal_align', 'center'),
                        'vertical_offset': overlay_settings.get('vertical_offset', 0),
                        'vertical_align': overlay_settings.get('vertical_align', 'top'),
                        'font_size': overlay_settings.get('font_size', 75),
                        'font': font_path,
                        'back_width': overlay_settings.get('back_width', 1920),
                        'back_height': overlay_settings.get('back_height', 125),
                        'back_color': overlay_settings.get('back_color', '#262626')
                    },
                    'plex_search': {
                        'all': {
                            'episode_label': values['label']
                        }
                    }
                }
            }
        }

        try:
            with open(overlay_file, 'w') as file:
                yaml.dump(overlay_content, file, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.error(f"Error creating overlay file {filename}: {str(e)}")
            success = False

    return success

def update_anime_episode_collections(config):
    """Update the anime episode type collections file in Kometa."""
    return sync_anime_episode_collections(config, force_update=True)

def setup_assets(config):
    """Setup all assets for DAKOSYS."""
    console.print("[bold blue]Setting up DAKOSYS assets...[/bold blue]")

    poster_result = setup_collection_posters(config)
    if poster_result:
        console.print("[green]Collection poster setup successfully[/green]")
    else:
        console.print("[yellow]Collection poster setup failed or skipped[/yellow]")

    font_result = setup_fonts(config)
    if font_result:
        console.print("[green]Fonts setup successfully[/green]")
    else:
        console.print("[yellow]Fonts setup failed or skipped[/yellow]")

    console.print("[blue]Setting up general assets...[/blue]")
    kometa_config_base = os.path.dirname(get_kometa_paths(config)[1]) 
    asset_directory_name = config.get('kometa_config', {}).get('asset_directory', 'config/assets')
    general_assets_dest_dir = os.path.join(kometa_config_base, asset_directory_name) 
    
    if ensure_directory(general_assets_dest_dir):
        gradient_files = ["gradient_top.png", "gradient_bottom.png"]
        for filename in gradient_files:
            gradient_source = os.path.join(CONTAINER_ASSETS_DIR, filename)
            gradient_dest = os.path.join(general_assets_dest_dir, filename)
            if os.path.exists(gradient_source):
                if copy_asset(gradient_source, gradient_dest):
                    console.print(f"[green]Gradient asset '{filename}' setup successfully[/green]")
                else:
                    console.print(f"[yellow]Gradient asset '{filename}' setup failed[/yellow]")
            else:
                logger.warning(f"Gradient asset not found in container: {gradient_source}")
                console.print(f"[yellow]Gradient asset not found: {gradient_source}[/yellow]")
    else:
        console.print("[yellow]Could not ensure general assets directory for Kometa config.[/yellow]")


    if config.get('services', {}).get('anime_episode_type', {}).get('enabled', False):
        console.print("[blue]Setting up anime episode type collections...[/blue]")
        collections_result = update_anime_episode_collections(config)
        if collections_result:
            console.print("[green]Anime episode collections setup successfully[/green]")
        else:
            console.print("[yellow]Anime episode collections setup failed[/yellow]")

        console.print("[blue]Setting up anime episode type overlays...[/blue]")
        overlays_result = create_anime_overlay_files(config)
        if overlays_result:
            console.print("[green]Anime episode overlays setup successfully[/green]")
        else:
            console.print("[yellow]Anime episode overlays setup failed[/yellow]")

    return True

if __name__ == "__main__":
    import yaml

    config_path = "/app/config/config.yaml" if os.environ.get('RUNNING_IN_DOCKER') == 'true' else "config/config.yaml"
    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)

        setup_result = setup_assets(config)

        if setup_result:
            with open(config_path, 'w') as file:
                yaml.dump(config, file)
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        console.print(f"[red]Error: {str(e)}[/red]")
