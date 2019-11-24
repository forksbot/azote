#!/usr/bin/env python3
# _*_ coding: utf-8 _*_

"""
Wallpaper manager for Sway, i3 and some other WMs, as a frontend to swaybg and feh

Author: Piotr Miller
e-mail: nwg.piotr@gmail.com
Website: http://nwg.pl
Project: https://github.com/nwg-piotr/azote
License: GPL3
"""
import os
import glob
import hashlib
import logging
from PIL import Image, ImageOps
import common
import pickle
import subprocess
import locale
import pkg_resources
import shutil

import json

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf, Gdk, GLib


def log(message, level=None):
    if common.logging_enabled:
        if level == "critical":
            logging.critical(message)
        elif level == "error":
            logging.error(message)
        elif level == "warning":
            logging.warning(message)
        elif level == "info":
            logging.info(message)
        else:
            logging.debug(message)


def str_to_bool(s):
    if s.upper() == 'TRUE':
        return True
    elif s.upper() == 'FALSE':
        return False
    else:
        raise ValueError


def check_displays():
    # Sway or not Sway? If so, the `swaymsg -t get_seats` command should return exit code 0
    try:
        result = subprocess.run(['swaymsg', '-t', 'get_seats'], stdout=subprocess.DEVNULL)
        common.sway = result.returncode == 0
    except:
        common.sway = False
    if common.sway:
        common.env['wm'] = 'sway'
    else:
        if os.getenv('XDG_SESSION_DESKTOP'):
            common.env['wm'] = os.getenv('XDG_SESSION_DESKTOP')
        elif os.getenv('DESKTOP_SESSION'):
            common.env['wm'] = os.getenv('DESKTOP_SESSION')
        else:
            common.env['wm'] = 'not sway'

    fnull = open(os.devnull, 'w')
    common.env['xrandr'] = subprocess.call(["which", "xrandr"], stdout=fnull, stderr=subprocess.STDOUT) == 0

    if common.sway:
        # We need swaymsg to check outputs on Sway
        try:
            displays = []
            json_string = subprocess.check_output("swaymsg -t get_outputs", shell=True).decode("utf-8").strip()
            outputs = json.loads(json_string)
            for output in outputs:
                if output['active']:  # dunno WTF xroot-0 is: i3 returns such an output with "active":false
                    display = {'name': output['name'],
                               'x': output['rect']['x'],
                               'y': output['rect']['y'],
                               'width': output['rect']['width'],
                               'height': output['rect']['height']}
                    displays.append(display)
                    log("Output found: {}".format(display), common.INFO)

            # Dummy display for testing
            """display = {'name': 'HDMI-A-2',
                       'x': 1920,
                       'y': 0,
                       'width': 1920,
                       'height': 1080}
            displays.append(display)
            log("Output: {}".format(display), common.INFO)"""

            # sort displays list by x, y: from left to right, then from bottom to top
            displays = sorted(displays, key=lambda x: (x.get('x'), x.get('y')))

            return displays

        except Exception as e:
            log("Failed checking displays: {}".format(e), common.ERROR)

    # On i3 we could use i3-msg here, but xrandr should also return what we need. If not on Sway - let's use xrandr
    elif common.env['xrandr']:
        names = subprocess.check_output("xrandr | awk '/ connected/{print $1}'", shell=True).decode(
            "utf-8").splitlines()
        res = subprocess.check_output("xrandr | awk '/*/{print $1}'", shell=True).decode("utf-8").splitlines()
        displays = []
        for i in range(len(names)):
            w_h = res[i].split('x')
            display = {'name': names[i],
                       'x': 0,
                       'y': 0,
                       'width': int(w_h[0]),
                       'height': int(w_h[1])}
            displays.append(display)
            log("Output found: {}".format(display), common.INFO)

        return displays

    else:
        log("Couldn't check displays", common.ERROR)
        exit(1)


def set_env(language=None):
    xdg_config_home = os.getenv('XDG_CONFIG_HOME')
    common.config_home = xdg_config_home if xdg_config_home else os.path.join(os.getenv("HOME"), ".config")
    common.azote_config_home = os.path.join(xdg_config_home, ".config/azote") if xdg_config_home else os.path.join(os.getenv("HOME"), ".config/azote")
    if not os.path.isdir(common.azote_config_home):
        os.mkdir(common.azote_config_home)

    xdg_data_home = os.getenv('XDG_DATA_HOME')
    common.data_home = xdg_data_home if xdg_data_home else os.path.join(os.getenv("HOME"), ".local/share/azote")
    if not os.path.isdir(common.data_home):
        os.mkdir(common.data_home)
    
    # MIGRATE DATA to XDG Base_Directory Specification - compliant folders
    # Up to v1.7.0 Azote used to store all the data here:
    common.app_dir = os.path.join(os.getenv("HOME"), ".azote")

    # Let's move all the content to their proper location, if not yet moved
    data_migrated = False
    migration_error = None
    if os.path.isdir(common.app_dir):
        try:
            azote_rc = os.path.join(common.app_dir, 'azoterc')
            if os.path.isfile(azote_rc):
                shutil.move(azote_rc, os.path.join(common.azote_config_home, 'azoterc'))

            azote_pkl = os.path.join(common.app_dir, 'settings.pkl')
            if os.path.isfile(azote_pkl):
                shutil.move(azote_pkl, os.path.join(common.data_home, 'settings.pkl'))

            bcg_feh_dir = os.path.join(common.app_dir, 'backgrounds-feh')
            if os.path.isdir(bcg_feh_dir):
                cmd = 'cp -rf {} {}'.format(bcg_feh_dir, os.path.join(common.data_home, 'backgrounds-feh'))
                os.system(cmd)

            bcg_sway_dir = os.path.join(common.app_dir, 'backgrounds-sway')
            if os.path.isdir(bcg_sway_dir):
                cmd = 'cp -rf {} {}'.format(bcg_sway_dir, os.path.join(common.data_home, 'backgrounds-sway'))
                os.system(cmd)

            data_migrated = True
        except Exception as e:
            migration_error = e

    if data_migrated:
        # Remove the old ~/.azote folder
        shutil.rmtree(common.app_dir)

    # logging
    common.log_file = os.path.join(common.data_home, "log.txt")
    logging.basicConfig(filename=common.log_file, format='%(asctime)s %(levelname)s: %(message)s', filemode='w',
                        level=logging.INFO)

    try:
        version = pkg_resources.require(common.app_name)[0].version
    except Exception as e:
        version = ' unknown version: {}'.format(e)

    log('Azote v{}'.format(version), common.INFO)
    
    if data_migrated:
        log('Data migrated to XDG-compliant folders', common.INFO)

    if migration_error:
        log('Data migration error: {}'.format(migration_error), common.ERROR)

    # We will preload the en_EN dictionary as default values
    common.lang = Language()

    if not language:
        # Lets check locale value
        # If running with LC_ALL=C, we'll get (None, None) here. Let's use en_EN in such case.
        lang = locale.getlocale()[0] if locale.getlocale()[0] is not None else 'en_EN'
    else:
        lang = language

    common.lang.load(lang)

    common.displays = check_displays()

    # thumbnails folder
    common.thumb_dir = os.path.join(common.data_home, "thumbnails")
    if not os.path.isdir(common.thumb_dir):
        os.mkdir(common.thumb_dir)

    # command file
    common.cmd_file = os.path.join(os.getenv("HOME"), ".azotebg")

    # temporary folder
    common.tmp_dir = os.path.join(common.data_home, "temp")
    if not os.path.isdir(common.tmp_dir):
        os.mkdir(common.tmp_dir)
    # remove all files inside on start
    for file in os.listdir(common.tmp_dir):
        path = os.path.join(common.tmp_dir, file)
        os.remove(path)  # clear on start
        log("Removed {}".format(path), common.INFO)

    # backgrounds folder
    name = 'backgrounds-sway' if common.sway else 'backgrounds-feh'
    common.bcg_dir = os.path.join(common.data_home, name)
    if not os.path.isdir(common.bcg_dir):
        os.mkdir(common.bcg_dir)

    # Sample folder (will be set on 1st run only)
    common.sample_dir = os.path.join(common.data_home, "sample")
    if not os.path.isdir(common.sample_dir):
        os.mkdir(common.sample_dir)
    shutil.copyfile('images/azote-wallpaper.jpg', os.path.join(common.sample_dir, 'azote-wallpaper.jpg'))
    shutil.copyfile('images/azote-wallpaper1.jpg', os.path.join(common.sample_dir, 'azote-wallpaper1.jpg'))
    shutil.copyfile('images/azote-wallpaper2.jpg', os.path.join(common.sample_dir, 'azote-wallpaper2.jpg'))

    # Sway comes with some sample wallpapers
    if common.sway and os.path.isdir('/usr/share/backgrounds/sway'):
        common.sample_dir = '/usr/share/backgrounds/sway'

    common.settings = Settings()
    if common.settings.clear_thumbnails:
        clear_thumbnails(clear_all=True)
        common.settings.clear_thumbnails = False

    log("Environment: {}".format(common.env), common.INFO)

    # check programs capable of opening files of allowed extensions
    if os.path.isfile('/usr/share/applications/mimeinfo.cache'):
        common.associations = {}  # Will stay None if the mimeinfo.cache file not found

        with open(os.path.join('/usr/share/applications/mimeinfo.cache')) as f:
            mimeinfo_cache = f.read().splitlines()

        for file_type in common.allowed_file_types:
            for line in mimeinfo_cache:
                if line.startswith('image/{}'.format(file_type)):
                    line = line.split('=')[1]  # cut out leading 'image/ext'
                    # Paths to .desktop files for opener names found
                    filenames = line[:-1].split(';')  # cut out trailing ';' to avoid empty last element after splitting
                    # prepend path
                    for i in range(len(filenames)):
                        filenames[i] = '/usr/share/applications/{}'.format(filenames[i])

                    data = []
                    for i in range(len(filenames)):
                        # Let's find the program Name= and Exec= in /usr/share/applications/shortcut_name.desktop
                        name, exe = '', ''

                        if os.path.isfile(filenames[i]):
                            with open(filenames[i]) as f:
                                rows = f.read().splitlines()
                                for row in rows:
                                    if row.startswith('Name='):
                                        name = row.split('=')[1]
                                    elif row.startswith('Name[{}]='.format(common.lang.lang[0:2])):
                                        name = row.split('=')[1]
                                    if row.startswith('Exec'):
                                        exe = row.split('=')[1].split()[0]
                                        continue
                            if name and exe:
                                data.append((name, exe))
                    common.associations[file_type] = data
                    """
                    Not necessarily all programs register jpg and jpeg extension (e.g. gimp registers jpeg only).
                    Let's create sets, join them and replace lists for both jpg and jpeg keys.
                    """
                    try:
                        jpg = set(common.associations['jpg'])
                        jpeg = set(common.associations['jpeg'])
                        together = jpg | jpeg
                        common.associations['jpg'] = together
                        common.associations['jpeg'] = together
                    except KeyError:
                        pass
                    # What if nothing found for 'jpg' or 'jpeg'?
                    if 'jpg' not in common.associations and 'jpeg' in common.associations:
                        common.associations['jpg'] = common.associations['jpeg']
                    elif 'jpeg' not in common.associations and 'jpg' in common.associations:
                        common.associations['jpeg'] = common.associations['jpg']

        log("Image associations: {}".format(common.associations), common.INFO)
    else:
        print('Failed opening /usr/share/applications/mimeinfo.cache')
        log("Failed creating image associations: /usr/share/applications/mimeinfo.cache file not found."
            " Setting feh as the only viewer.", common.ERROR)
    
    # Check if packages necessary to pick colours from the screen available
    try:
        magick = subprocess.run(['convert', '-version'], stdout=subprocess.DEVNULL).returncode == 0
    except FileNotFoundError:
        magick = False
    av = 'found' if magick else 'not found'
    log("imagemagick library {}".format(av), common.INFO)
    
    if common.sway:
        try:
            grim = subprocess.run(['grim', '-h'], stdout=subprocess.DEVNULL).returncode == 0
        except FileNotFoundError:
            grim = False
        av = 'found' if grim else 'not found'
        log("grim package {}".format(av), common.INFO)
    
        try:
            slurp = subprocess.run(['slurp', '-h'], stdout=subprocess.DEVNULL).returncode == 0
        except FileNotFoundError:
            slurp = False
        av = 'found' if slurp else 'not found'
        log("slurp package {}".format(av), common.INFO)
    
        if magick and grim and slurp:
            log("Pick color from screen feature enabled", common.INFO)
            common.picker = True
        else:
            log("Pick color from screen feature needs imagemagick, grim and slurp packages packages", common.WARNING)
    else:
        try:
            maim = subprocess.run(['maim', '-h'], stdout=subprocess.DEVNULL).returncode == 0
        except FileNotFoundError:
            maim = False
        av = 'found' if maim else 'not found'
        log("maim package {}".format(av), common.INFO)

        try:
            slop = subprocess.run(['slop', '-h'], stdout=subprocess.DEVNULL).returncode == 0
        except FileNotFoundError:
            slop = False
        av = 'found' if slop else 'not found'
        log("slurp package {}".format(av), common.INFO)

        if magick and maim and slop:
            log("Pick color from screen - feature available", common.INFO)
            common.picker = True
        else:
            log("Pick color from screen feature needs imagemagick, maim and slop packages installed", common.WARNING)
            
    # Find dotfiles
    if os.path.isfile(os.path.join(common.config_home, 'alacritty/alacritty.yml')):
        common.alacritty_config = os.path.join(common.config_home, 'alacritty/alacritty.yml')
    elif os.path.isfile(os.path.join(os.getenv('HOME'), '.alacritty.yml')):
        common.alacritty_config = os.path.join(os.getenv('HOME'), '.alacritty.yml')

    msg = common.alacritty_config if common.alacritty_config else 'not found'
    log('Alacritty config file: {}'.format(msg), common.INFO)
    if common.alacritty_config and not common.env['yaml']:
        log("python yaml module not found - alacritty.yml toolbox disabled", common.WARNING)
    
    if os.path.isfile(os.path.join(os.getenv('HOME'), '.Xresources')):
        common.xresources = os.path.join(os.getenv('HOME'), '.Xresources')
        log('{} file found'.format(common.xresources), common.INFO)
    else:
        log('~/.Xresources file not found', common.INFO)


def copy_backgrounds():
    # Clear current folder content
    for file in os.listdir(common.bcg_dir):
        os.remove(os.path.join(common.bcg_dir, file))
    # Copy manipulated (flip, split) files from the temporary folder
    for file in os.listdir(common.tmp_dir):
        shutil.copyfile(os.path.join(common.tmp_dir, file), os.path.join(common.bcg_dir, file))


def hash_name(full_path):
    """
    Thumbnail path -> name (w/o extension)
    :param full_path: original file path
    :return: MD5-hashed path
    """
    return hashlib.md5(full_path.encode()).hexdigest()


def create_thumbnails(scr_path):
    # Let's count allowed files first
    common.progress_bar.hide()
    counter = 0
    for extension in common.allowed_file_types:
        for in_path in glob.glob(os.path.join(scr_path, "*.{}".format(extension))):
            if file_allowed(in_path):
                counter += 1
    if counter > 0:
        # get all the files of allowed types from current path
        common.progress_bar.show()
        common.progress_bar.set_fraction(0.0)
        processed = 0
        for extension in common.allowed_file_types:
            for in_path in glob.glob(os.path.join(scr_path, "*.{}".format(extension))):
                if file_allowed(in_path):
                    thumb_name = "{}.png".format(hash_name(in_path))
                    dest_path = os.path.join(common.thumb_dir, thumb_name)
                    if not os.path.isfile(dest_path):
                        create_thumbnail(in_path, dest_path, thumb_name)
                    elif is_newer(in_path, dest_path):
                        create_thumbnail(in_path, dest_path, thumb_name, True)
                    processed += 1
                    common.progress_bar.set_fraction(processed / counter)
                    common.progress_bar.set_text(str(processed))
                    while Gtk.events_pending():
                        Gtk.main_iteration()
    common.progress_bar.hide()


def create_thumbnail(in_path, dest_path, thumb_name, refresh=False):
    action = 'New thumb' if not refresh else 'Refresh'
    try:
        img = Image.open(in_path)
        # convert to thumbnail image
        img.thumbnail(common.settings.thumb_size, Image.ANTIALIAS)

        img = expand_img(img)

        img.save(dest_path, "PNG")
        log('{}: {} -> {}'.format(action, in_path, thumb_name), common.INFO)
    except Exception as e:
        log('{} - {}'.format(action, e), common.ERROR)


def flip_selected_wallpaper():
    """
    This creates vertically flipped image and its thumbnail and saves to ~/.azote/backgrounds
    :return: thumbnail path, flipped image path
    """
    if common.selected_wallpaper:
        try:
            img = Image.open(common.selected_wallpaper.source_path)
            flipped = img.transpose(Image.FLIP_LEFT_RIGHT)
            img_path = os.path.join(common.bcg_dir, "flipped-{}".format(common.selected_wallpaper.filename))
            flipped.save(os.path.join(common.tmp_dir, "flipped-{}".format(common.selected_wallpaper.filename)), "PNG")

            flipped.thumbnail(common.settings.thumb_size, Image.ANTIALIAS)
            flipped = expand_img(flipped)

            thumb_path = os.path.join(common.tmp_dir, "thumbnail-{}".format(common.selected_wallpaper.filename))
            flipped.save(thumb_path, "PNG")
            return thumb_path, img_path

        except Exception as e:
            log('Failed flipping {} - {}'.format(common.selected_wallpaper.source_path, e), common.ERROR)


def split_selected_wallpaper(num_parts):
    try:
        img = Image.open(common.selected_wallpaper.source_path)
        width, height = img.size
        part_width = width // num_parts
        paths_list = []
        for i in range(num_parts):
            box = (i * part_width, 0, i * part_width + part_width, height)
            part = img.crop(box)
            img_path = os.path.join(common.bcg_dir, "part{}-{}".format(i, common.selected_wallpaper.filename))
            part.save(os.path.join(common.tmp_dir, "part{}-{}".format(i, common.selected_wallpaper.filename)), "PNG")

            part.thumbnail(common.settings.thumb_size, Image.ANTIALIAS)

            thumb_path = os.path.join(common.tmp_dir, "thumb-part{}-{}".format(i, common.selected_wallpaper.filename))

            part = expand_img(part)

            part.save(thumb_path, "PNG")
            paths = (img_path, thumb_path)
            paths_list.append(paths)
        return paths_list

    except Exception as e:
        log('Failed splitting {} - {}'.format(common.selected_wallpaper.source_path, e), common.ERROR)


def expand_img(image):
    # We want the thumbnail to be always in the same proportion. Let's expand if necessary.
    width, height = image.size
    border_h = (common.settings.thumb_width - width) // 2
    border_v = (common.settings.thumb_height - height) // 2
    if border_v > 0 or border_h > 0:
        # border = (border_h, border_v, border_h, border_v)
        # return ImageOps.expand(image, border=border)
        # Let's add checkered background instead of the black one
        background = Image.open('images/squares.jpg')
        background = background.resize(common.settings.thumb_size, Image.ANTIALIAS)
        background.paste(image, (border_h, border_v))
        return background
    else:
        return image


def scale_and_crop(item, image_path, width, height):
    img = Image.open(image_path)

    # We can either scale vertically & crop horizontally or scale horizontally and crop vertically
    new_height = int(img.size[0] * height / width)

    if new_height < img.size[1]:  # we need to scale to display width and crop vertical margins
        new_height = int(width * img.size[1] / img.size[0])
        # Choose the filter depending on if we're scaling down or up
        if new_height >= height:
            img = img.resize((width, new_height), Image.ANTIALIAS)
        else:
            img = img.resize((width, new_height), Image.BILINEAR)

        margin = (img.size[1] - height) // 2
        img = img.crop((0, margin, width, height + margin))

    elif new_height > img.size[1]:  # we need to scale to display height and crop horizontal margins
        new_width = int(img.size[0] * height / img.size[1])
        if new_width >= width:
            img = img.resize((new_width, height), Image.ANTIALIAS)
        else:
            img = img.resize((new_width, height), Image.BILINEAR)

        margin = (img.size[0] - width) // 2
        img = img.crop((margin, 0, width + margin, height))

    else:
        img = img.resize((width, height), Image.ANTIALIAS)

    img.save('{}-{}x{}{}'.format(os.path.splitext(image_path)[0], width, height, os.path.splitext(image_path)[1]))
    common.preview.refresh()


def is_newer(in_path, dest_path):
    return os.path.getmtime(in_path) > os.path.getmtime(dest_path)


def file_allowed(path):
    ext = path.split('.')[-1].lower()
    return ext in common.allowed_file_types


def update_status_bar():
    num_files = 0
    total_size = 0
    if os.path.isdir(common.thumb_dir):
        for file in os.listdir(common.thumb_dir):
            num_files += 1
            file_info = os.stat(os.path.join(common.thumb_dir, file))
            total_size += file_info.st_size
    common.status_bar.push(0, common.lang['thumbnails_in_cache'].format(num_files, convert_bytes(total_size)))
    
    
def clear_thumbnails(clear_all=False):
    files_in_use = os.listdir(common.settings.src_path)
    for i in range(len(files_in_use)):
        full_path = os.path.join(common.settings.src_path, files_in_use[i])
        files_in_use[i] = '{}.png'.format(hashlib.md5(full_path.encode()).hexdigest())
    
    number = 0
    for file in os.listdir(common.thumb_dir):
        if file not in files_in_use or clear_all:
            file_path = os.path.join(common.thumb_dir, file)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    number += 1
            except Exception as e:
                print(e)
    msg = 'thumbnails' if clear_all else 'unused thumbnails'
    print('\nAzote: {} {} deleted\n'.format(number, msg))


def convert_bytes(num):
    """
    https://stackoverflow.com/a/39988702/4040598
    """
    for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0


def create_pixbuf(size, color):
    image = Image.new("RGB", size, color)
    data = image.tobytes()
    w, h = image.size
    data = GLib.Bytes.new(data)
    return GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, False, 8, w, h, w * 3)


class Settings(object):
    def __init__(self):
        # Settings available in GUI we'll store in a pickle file
        self.file = os.path.join(common.data_home, "settings.pkl")

        self.src_path = common.sample_dir
        self.sorting = 'new'
        # Gtk.Menu() on sway is unreliable, especially called with right click
        self.custom_display = None
        self.old_thumb_width = None
        self.clear_thumbnails = False
        self.copy_as = '#rgb'
        self.color_dictionary = False
        self.image_menu_button = False

        # Runtime config (json) location
        self.rc_file = os.path.join(common.azote_config_home, "azoterc")
        
        self.load()

    def load(self):
        save_needed = False
        if not os.path.isfile(self.file):
            log('Creating initial settings', common.INFO)
            self.save()

        with open(self.file, 'rb') as input_data:
            settings = pickle.load(input_data)

        # Do not read if it's inside old folders (before data migration); save default value instead
        if not settings.src_path == os.path.join(os.getenv('HOME'), '.azote/sample'):
            self.src_path = settings.src_path
        else:
            save_needed = True

        try:
            self.sorting = settings.sorting  # 'new' 'old' 'az' 'za'
            log('Image sorting: {}'.format(self.sorting), common.INFO)
        except AttributeError:
            save_needed = True

        try:
            self.custom_display = settings.custom_display
            log('Custom display: {}'.format(self.custom_display), common.INFO)
        except AttributeError:
            save_needed = True

        try:
            self.old_thumb_width = settings.old_thumb_width
            log('Old thumbnail width: {}'.format(self.old_thumb_width), common.INFO)
        except AttributeError:
            save_needed = True
            
        try:
            self.copy_as = settings.copy_as
        except AttributeError:
            save_needed = True
            
        try:
            self.color_dictionary = settings.color_dictionary
        except AttributeError:
            save_needed = True

        try:
            self.image_menu_button = settings.image_menu_button
        except AttributeError:
            save_needed = True

        self.load_rc()
        # overwrite self.old_thumb_width with self.thumb_width if changed in azoterc
        if self.old_thumb_width != self.thumb_width:
            self.old_thumb_width = self.thumb_width
            save_needed = True
            log('New thumbnail width: {}, clearing existing thumbnails!'.format(self.thumb_width), common.WARNING)
            self.clear_thumbnails = True

        if save_needed:
            self.save()

    def save(self):
        with open(self.file, 'wb') as output:
            pickle.dump(self, output, pickle.HIGHEST_PROTOCOL)
            
    def load_rc(self):
        save_needed = False
        try:
            with open(self.rc_file, 'r') as f:
                rc = json.load(f)
        except FileNotFoundError:
            log('rc file not found, creating...', common.INFO)
            self.save_rc(set_defaults=True)

        try:
            with open(self.rc_file, 'r') as f:
                rc = json.load(f)
            log('rc file loaded', common.INFO)
        except Exception as e:
            log('rc file error: {}'.format(e), common.ERROR)

        try:
            self.thumb_width = int(rc['thumb_width'])
            # ignore too small values
            if self.thumb_width < 128:
                self.thumb_width = 128
        except KeyError:
            self.thumb_width = 240
            save_needed = True

        self.thumb_height = int(self.thumb_width * 135 / 240)
        self.thumb_size = (self.thumb_width, self.thumb_height)
        log('Thumbnail size: {}'.format(self.thumb_size), common.INFO)
            
        try:
            self.columns = int(rc['columns'])
        except KeyError:
            self.columns = 3
            save_needed = True
        log('Number of columns: {}'.format(self.columns), common.INFO)

        try:
            self.color_icon_w = int(rc['color_icon_w'])
        except KeyError:
            self.color_icon_w = 100
            save_needed = True

        try:
            self.color_icon_h = int(rc['color_icon_h'])
        except KeyError:
            self.color_icon_h = 50
            save_needed = True

        try:
            self.clip_prev_size = int(rc['clip_prev_size'])
        except KeyError:
            self.clip_prev_size = 30
            save_needed = True

        try:
            self.palette_quality = int(rc['palette_quality'])
        except KeyError:
            self.palette_quality = 10
            save_needed = True
        log('Palette quality: {} (10 by default, the less, the better & slower)'.format(self.palette_quality), common.INFO)

        if save_needed:
            self.save_rc()

    def save_rc(self, set_defaults=False):
        if set_defaults:
            self.thumb_width = 240
            self.columns = 3
            self.color_icon_w = 100
            self.color_icon_h = 50
            self.clip_prev_size = 30
            self.palette_quality = 10

        rc = {'thumb_width': str(self.thumb_width),
              'columns': str(self.columns),
              'color_icon_w': str(self.color_icon_w),
              'color_icon_h': str(self.color_icon_h),
              'clip_prev_size': str(self.clip_prev_size),
              'palette_quality': str(self.palette_quality)}
        
        with open(self.rc_file, 'w') as f:
            json.dump(rc, f, indent=2)


class Language(dict):
    def __init__(self):
        super().__init__()
        self.lang = 'en_EN'
        # We'll initialize with values from en_EN
        with open(os.path.join('languages', 'en_EN')) as f:
            lines = f.read().splitlines()
            for line in lines:
                if line and not line.startswith('#'):
                    pair = line.split('=')
                    key, value = pair[0].strip(), pair[1].strip()
                    self[key] = value

    def load(self, lang):
        try:
            # Overwrite initial values if translation found
            with open(os.path.join('languages', lang)) as f:
                lines = f.read().splitlines()
                for line in lines:
                    if line and not line.startswith('#'):
                        pair = line.split('=')
                        key, value = pair[0].strip(), pair[1].strip()
                        self[key] = value
            self.lang = lang
            log("Loaded lang: {}".format(lang), common.INFO)

        except FileNotFoundError:
            log("Couldn't load lang: {}".format(lang), common.WARNING)
