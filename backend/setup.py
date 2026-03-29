from setuptools import setup, find_packages

setup(
    name="stock-analysis-backend",
    version="0.1.0",
    license="PolyForm Noncommercial 1.0.0",
    packages=find_packages(),
    install_requires=[
        "python-dotenv",
        "sqlalchemy",
        "psycopg2-binary",
        "pandas",
        "numpy",
        "tiktoken",
        "google-generativeai",
        "finnhub-python",
        "beautifulsoup4",
        "requests",
        "fastapi",
        "uvicorn[standard]",
        "yfinance",
        "playwright",
        "rapidfuzz",
        "lxml",
    ],
    python_requires=">=3.8",
)
