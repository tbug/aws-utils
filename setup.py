from setuptools import setup

setup(
    name='awsutils',
    version='0.1',
    py_modules=['cli'],
    install_requires=[
        'Click', 'boto3'
    ],
    entry_points='''
        [console_scripts]
        awsutils=cli:cli
    '''
)