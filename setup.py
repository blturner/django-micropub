from setuptools import find_packages, setup

setup(
    name="django-micropub",
    version="0.1",
    description="A micropub server.",
    url="http://github.com/blturner/django-micropub",
    author="Benjamin Turner",
    author_email="ben@benjaminturner.me",
    license="MIT",
    packages=find_packages(),
    zip_safe=False,
)
