import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from xml.dom import minidom

from conans import CMake, ConanFile, tools


class QtBreezeIconsConan(ConanFile):
    name = 'qt-breeze-icons'
    version = os.getenv('KDE_VERSION', '5.74.0')
    license = 'LGPL-2.1-only'
    description = 'Conan recipe for using Breeze icons as a Qt icon theme'
    url = 'https://github.com/DragoonBoots/qt-breeze-icons'
    topics = ["Qt"]
    no_copy_source = True
    options = dict(pattern='ANY')
    default_options = dict(pattern='.+')

    def source(self):
        git = tools.Git(folder='breeze-icons')
        git.clone('https://invent.kde.org/frameworks/breeze-icons.git', branch='v{}'.format(self.version), shallow=True)

    def _configure_cmake(self) -> CMake:
        cmake = CMake(self)
        # This will create generated icons (e.g. 24x24 versions)
        cmake.configure(source_dir='breeze-icons',
                        defs={'BINARY_ICONS_RESOURCE': False, 'SKIP_INSTALL_ICONS': True})
        return cmake

    def _icon_paths(self, path: Path):
        """Iterate through the given directory for requested icon files"""
        if path.is_dir():
            for child in path.iterdir():
                yield from self._icon_paths(child)
        elif path.is_file():
            if path.suffix == '.svg' and re.fullmatch(str(self.options.pattern), path.stem) is not None:
                yield path

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
        # Hold a list of installed icons for copying
        qrc_paths = []
        for theme in icon_themes:
            source_icons = Path(self.source_folder) / 'breeze-icons' / theme.dir_name
            generated_icons = Path(self.build_folder) / theme.dir_name / 'generated'
            dirs = (source_icons, generated_icons)
            for directory in dirs:
                for path in self._icon_paths(directory):
                    qrc_paths.extend(
                        self.copy(str(path.relative_to(directory)), src=str(directory),
                                  dst='share/{}'.format(theme.name), symlinks=True))
            qrc_paths.extend(self.copy('index.theme', src=str(source_icons), dst='share/{}'.format(theme.name)))

        # Generate the QRC
        root = ET.Element('RCC', {'version': '1.0'})
        qresource = ET.SubElement(root, 'qresource', {'prefix': '/icons'})
        for path in qrc_paths:
            rel_path = Path(path).relative_to(Path(self.package_folder) / 'share')
            file = ET.SubElement(qresource, 'file')
            file.text = str(rel_path)
        qrc_file_path = Path(self.build_folder) / 'breeze-icons.qrc'
        out = '<!DOCTYPE RCC>' + os.linesep + ET.tostring(root, encoding='unicode', xml_declaration=False)
        with qrc_file_path.open('wt') as qrc_file:
            qrc_file.write(minidom.parseString(out).toprettyxml())
        self.copy(str(qrc_file_path.relative_to(self.build_folder)), dst='share', keep_path=False)

    def package_info(self):
        self.cpp_info.name = 'BreezeIcons'
        self.cpp_info.resdirs = ["share"]

    def package_id(self):
        self.info.header_only()
