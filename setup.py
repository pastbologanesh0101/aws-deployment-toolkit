from setuptools import find_packages, setup

setup(
    name="aws-deployment-toolkit",
    version="0.1.0",
    description="A small CLI toolkit for S3 sync, Lambda deploy, and CloudFormation deploy.",
    packages=find_packages(include=["aws_deployment_toolkit", "aws_deployment_toolkit.*"]),
    include_package_data=True,
    package_data={"aws_deployment_toolkit": ["templates/*.yaml"]},
    install_requires=[
        "boto3>=1.34",
        "click>=8.1",
    ],
    entry_points={
        "console_scripts": [
            "adt=aws_deployment_toolkit.cli:main",
        ],
    },
    python_requires=">=3.9",
)
