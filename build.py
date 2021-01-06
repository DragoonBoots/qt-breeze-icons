from cpt.packager import ConanMultiPackager

if __name__ == "__main__":
    builder = ConanMultiPackager()
    # No settings/options are necessary, this is header only
    builder.add(settings={}, options={}, env_vars={}, build_requires={})
    builder.run()
