[app]

# (str) Title of your application
title = Invoice Generator

# (str) Package name
package.name = invoicegenerator

# (str) Package domain (needed for android/ios packaging)
package.domain = org.invoicegenerator

# (source.dir) Source code where the main.py is located
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas

# (list) List of inclusions using pattern matching
#source.include_patterns = assets/*,images/*.png

# (list) Source files to exclude (let empty to not exclude anything)
#source.exclude_exts = spec

# (list) List of directory to exclude (let empty to not exclude anything)
#source.exclude_dirs = tests, bin

# (list) List of exclusions using pattern matching
#source.exclude_patterns = license,images/*/*.png

# (str) Application versioning (method 1)
version = 1.0.0

# (str) Application versioning (method 2)
# version.regex = __version__ = ['"](.*)['"]
# version.filename = %(source.dir)s/main.py

# (list) Application requirements
# comma separated e.g. requirements = sqlite3,kivy
requirements = python3,kivy,flet,fpdf

# (str) Supported orientation (landscape, portrait or all)
orientation = portrait

# (list) List of service to declare
#services = org.test.myservice:./service.py

#
# Android specific
#

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (string) Presplash of the application (image or text+image)
# presplash.filename = %(source.dir)s/data/presplash.png
# presplash.show_during_load = true
# presplash.overlay_filex = %(source.dir)s/data/presplash_overlay.png

# (list) Permissions
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,ACCESS_MEDIA_LOCATION,MANAGE_EXTERNAL_STORAGE

# (int) Target Android API, should be as high as possible.
android.api = 31

# (int) Minimum API your APK will support.
android.minapi = 21

# (str) Android NDK version to use
#android.ndk = 21b

# (bool) Use --private data storage (True) or --dir public storage (False)
#android.private_storage = True

# (str) Android app theme, default is ok for Kivy-based app
# android.theme = "@android:style/Theme.NoTitleBar"

# (bool) Copy library instead of making a libpymodules.so
#android.copy_libs = 1

# (str) The Android arch to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
android.archs = arm64-v8a,armeabi-v7a

# (bool) Enable AndroidX support
android.enable_androidx = True

# (str) Android logcat filters to use
#android.logcat_filters = *:S python:D

# (bool) Copy library instead of making a libpymodules.so
#android.copy_libs = 1

# (str) The Android arch to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
android.archs = arm64-v8a

# (bool) Enable AndroidX support
android.enable_androidx = True

# (list) Pattern to whitelist for the whole project
#android.whitelist = lib-dynload/termios.so

# (str) Path to a Java file for the Android Java API to add support for
# access to the Permission API in Android 6 (API 23) and higher
#android.add_src = java/src/android/permissions/Permissions.java

# (list) Android application meta-data (key=value format)
android.meta_data = com.google.android.gms.version=@integer/google_play_services_version

# (str) Filename of OUYA Console icon. It must be a 732x412 png image.
#android.ouya_xml = %(source.dir)s/data/ouya_icon.xml

# (str) XML file for custom backup rules (see the documentation)
# android.backup_rules = %(source.dir)s/data/backup_rules.xml

# (str) XML file for custom restore rules (see the documentation)
# android.restore_rules = %(source.dir)s/data/restore_rules.xml

# (list) Icons. The first icon is used as launcher icon. For example:
# android.icon_filename = %(source.dir)s/data/icon.png

# (str) Path to the directory containing application resources, if
# empty, and no other resources are declared, the app icon and presplash
# will be used.
# android.res_dir = %(source.dir)s/res

# (str) Path to the directory containing application resources, if
# empty, and no other resources are declared, the app icon and presplash
# will be used.
# android.assets_dir = %(source.dir)s/assets

# (list) Pattern to whitelist for the whole project
#android.whitelist = lib-dynload/termios.so

# (str) Android app theme, default is ok for Kivy-based app
# android.theme = "@android:style/Theme.NoTitleBar"

# (bool) Copy library instead of making a libpymodules.so
#android.copy_libs = 1

# (str) The Android arch to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
#android.archs = arm64-v8a

# (bool) Enable AndroidX support
#android.enable_androidx = True

# (str) Android application meta-data (key=value format)
#android.meta_data = 

# (str) Filename of OUYA Console icon. It must be a 732x412 png image.
#android.ouya_xml = %(source.dir)s/data/ouya_icon.xml

# (str) XML file for custom backup rules (see the documentation)
# android.backup_rules = %(source.dir)s/data/backup_rules.xml

# (str) XML file for custom restore rules (see the documentation)
# android.restore_rules = %(source.dir)s/data/restore_rules.xml

# (bool) Indicate if the application should be fullscreen or not
#android.fullscreen = 0

# (list) Supported orientations
# Valid values: landscape, portrait
#android.orientation = landscape

# (bool) Indicate if the application should be fullscreen or not
#android.fullscreen = 0

# (list) Supported orientations
# Valid values: landscape, portrait
#android.orientation = landscape

# (bool) Indicate if the application should be fullscreen or not
#android.fullscreen = 0

# (str) Android logcat filters to use
#android.logcat_filters = *:S python:D

# (bool) Copy library instead of making a libpymodules.so
#android.copy_libs = 1

# (str) The Android arch to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
#android.archs = arm64-v8a

#
# Python for android (p4a) specific
#

# (str) python for android directory (if empty, it will be automatically downloaded.)
#p4a.dir = ../python-for-android/

# (str) The bootstrap to use. Leave empty to let python-for-android choose.
#p4a.bootstrap = sdl2

# (int) port number to specify an explicit --port= p4a argument (eg for bootstrap flask)
#p4a.port = 5000

#
# iOS specific
#

# (bool) Whether or not to sign the code
ios.codesign.allowed = False

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning on buildozer run
warn_on_root = 1
