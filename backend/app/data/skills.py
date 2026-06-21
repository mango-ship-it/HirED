"""A vocabulary of recognizable skills for matching against job-description text.

Used to surface the real in-demand skills from scraped postings (jd_skills.py).
Display casing is preserved; matching is case-insensitive substring. Deliberately
excludes ambiguous short tokens (e.g. "Go", "R", "C") that would match noise.
"""

from __future__ import annotations

SKILL_VOCAB: list[str] = [
    # languages
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Ruby", "Swift",
    "Kotlin", "PHP", "Scala", "SQL", "NoSQL", "HTML", "CSS",
    # web / backend
    "React", "Angular", "Vue", "Next.js", "Node.js", "Django", "Flask", "FastAPI",
    "Spring", ".NET", "Rails", "GraphQL", "REST API", "Microservices",
    # cloud / devops
    "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "CI/CD", "Git",
    "Linux", "Jenkins",
    # data / ml
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Kafka", "Spark", "Hadoop",
    "Airflow", "dbt", "Snowflake", "Pandas", "NumPy", "PyTorch", "TensorFlow",
    "scikit-learn", "Machine Learning", "Deep Learning", "NLP", "Computer Vision",
    "Data Analysis", "Data Engineering", "ETL", "A/B Testing", "Statistics",
    "Tableau", "Power BI", "Excel",
    # product / design / marketing / business
    "Figma", "UX", "UI", "Product Management", "Project Management", "Agile",
    "Scrum", "Jira", "SEO", "Google Analytics", "Content Marketing", "Social Media",
    "Salesforce", "HubSpot", "Copywriting", "Accounting", "Financial Modeling",
    "Communication", "Leadership", "Stakeholder Management", "Public Speaking",
]
