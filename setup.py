from setuptools import setup

setup(name='tofu',
      version='0.1',
      description="""A TerraForm OpenStack dynamic inventory
                   script that parses the JSON object from
                   terraform state pull to generate a YAML or JSON
                   blurb that is suitable for an ansible dynamic inventory""",
      url='https://github.com/shalomb/tofu',
      author='Shalom Bhooshi',
      license='Apache License 2.0',
      packages=['tofu'],
      zip_safe=False,
      scripts=['tofu/tofu.py']
    )
