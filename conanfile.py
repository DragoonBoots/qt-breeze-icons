import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from xml.dom import minidom

from conans import CMake, ConanFile, tools


class QtBreezeIconsConan(ConanFile):
    name = 'qt-breeze-icons'
    kde_stable_version = '5.77.0'
    license = 'LGPL-2.1-only'
    description = 'Conan recipe for using Breeze icons as a Qt icon theme'
    url = 'https://github.com/DragoonBoots/qt-breeze-icons'
    topics = ["Qt"]
    no_copy_source = True
    exports = ('version.txt',)
    options = dict(pattern='ANY')
    default_options = dict(pattern=None)

    def _get_version(self):
        version_file_path = Path(self.recipe_folder) / 'version.txt'
        if version_file_path.is_file():
            with version_file_path.open(mode='rt') as version_file:
                return version_file.readline().strip()
        else:
            return self.kde_stable_version

    def set_version(self):
        self.version = self._get_version()

    def build_requirements(self):
        self.build_requires("ECM/{}@dragoonboots/stable".format(self._get_version()))

    def source(self):
        # Zip downloads cause corrupted symlinks, so git clone is required
        git = tools.Git()
        git.clone('https://invent.kde.org/frameworks/breeze-icons.git', branch='v{}'.format(self.version), shallow=True)

    def _configure_cmake(self) -> CMake:
        cmake = CMake(self)
        cmake.definitions['ECM_DIR'] = str(Path(self.deps_cpp_info['ECM'].res_paths[0]) / 'ECM' / 'cmake')
        cmake.definitions['BINARY_ICONS_RESOURCE'] = False
        cmake.definitions['SKIP_INSTALL_ICONS'] = True
        cmake.definitions['WITH_ICON_GENERATION'] = False
        # This will create generated icons (e.g. 24x24 versions)
        cmake.configure()
        return cmake

    def _icon_paths(self, path):
        """Iterate through the given directory for requested icon files"""
        for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
            for file in filenames:
                stem, ext = os.path.splitext(file)
                matched = (not self.options.pattern) or re.fullmatch(str(self.options.pattern), stem) is not None
                if ext == '.svg' and matched:
                    yield os.path.join(dirpath, file)
            for child in dirnames:
                yield from self._icon_paths(os.path.join(dirpath, child))

    def build(self):
        cmake = self._configure_cmake()
        cmake.build()

    def package(self):
        # Don't use cmake install to allow for filtering and doctoring the generated QRC
        @dataclass
        class IconTheme:
            name: str
            dir_name: str

        icon_themes = (
            IconTheme(name='breeze-light', dir_name='icons'),
            IconTheme(name='breeze-dark', dir_name='icons-dark'),
        )
        # Hold a list of installed icons for copying and generate the QRC
        root = ET.Element('RCC', {'version': '1.0'})
        qresource = ET.SubElement(root, 'qresource', {'prefix': '/icons'})
        for theme in icon_themes:
            source_icons = os.path.join(self.source_folder, theme.dir_name)
            generated_icons = os.path.join(self.build_folder,  theme.dir_name, 'generated')
            dirs = (source_icons, generated_icons)
            for directory in dirs:
                for path in self._icon_paths(directory):
                    copied = self.copy(os.path.relpath(path, directory), src=str(directory),
                                       dst='share/{}'.format(theme.name), symlinks=True)
                    for new_path in copied:
                        print('Adding {}'.format(new_path))
                        file = ET.SubElement(qresource, 'file')
                        file.text = os.path.relpath(new_path, os.path.join(self.package_folder, 'share'))
            # Copy theme file and add to QRC
            for theme_path in self.copy('index.theme', src=str(source_icons), dst='share/{}'.format(theme.name)):
                file = ET.SubElement(qresource, 'file')
                file.text = os.path.relpath(theme_path, os.path.join(self.package_folder, 'share'))

        # Generate the QRC
        print("Creating QRC")
        qrc_file_path = Path(self.build_folder) / 'breeze-icons.qrc'
        out = '<!DOCTYPE RCC>' + os.linesep + ET.tostring(root, encoding='unicode', xml_declaration=False)
        with qrc_file_path.open('wt') as qrc_file:
            qrc_file.write(minidom.parseString(out).toprettyxml())
        self.copy(str(qrc_file_path.relative_to(self.build_folder)), dst='share', keep_path=False)

    def package_info(self):
        self.cpp_info.name = 'BreezeIcons'
        self.cpp_info.resdirs = ["share"]
