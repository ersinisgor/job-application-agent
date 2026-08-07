# PROJECTS LIST

IMPORTANT:
Only use the technologies and information provided here when modifying or adding projects to the CV.
Do not invent project details.

### 1. API Hotel Project

**Explanation**

ApiHotelProject is a hotel management system built on .NET 10: a layered ASP.NET Core Web API backend, an ASP.NET Core MVC front end with a public hotel site and an admin dashboard, and SQL Server for storage. It offers user authentication with roles, booking and room management, staff/service/testimonial management, SMTP mail and file upload. The project was migrated from .NET 5 to .NET 10 (LTS), containerized with Docker and deployed live to Google Cloud Run against an Azure SQL Database. Both applications ship in a single container image: the Web API listens on loopback only and the MVC front end is the sole public process, talking to the API over HTTP.

Live demo: https://hotel-demo-453942543225.europe-west1.run.app

**Technologies Used**

**Backend**

* .NET 10 (LTS)
* ASP.NET Core Web API
* Entity Framework Core 10
* MS SQL Server / Azure SQL Database
* ASP.NET Core Identity (cookie authentication, roles)
* Data Protection with EF Core key storage
* AutoMapper
* Fluent Validation
* Swagger (Swashbuckle)
* MailKit (SMTP)
* Repository Design Pattern
* N-Tier Architecture
* DTO Layer
* Dependency Injection
* OOP

**Frontend**

* ASP.NET Core MVC
* Razor Views
* View Components
* Bootstrap 5
* HTML
* CSS
* JavaScript

**DevOps & Tools**

* Docker (multi-stage build)
* Google Cloud Run
* Google Secret Manager
* Postman
* Git

---

### 2. Movie App MERN

**Explanation**

This project is a movie streaming platform built using the MERN stack (MongoDB, Express.js, React.js, Node.js). It mimics the core functionalities of modern streaming services. Users can sign up, log in, explore trending movies and TV shows, watch trailers, search for actors and movies, and maintain a search history. Authentication is handled using JWT. The application includes a responsive interface optimized for desktop, tablet, and mobile devices.

**Technologies Used**

**Frontend**

* React.js
* React Router
* Axios
* Lucide React
* Zustand
* React Player
* Tailwind CSS
* React Hot Toast

**Backend**

* Node.js
* Express.js
* MongoDB
* Mongoose
* bcryptjs
* JSON Web Token (JWT)
* Cookie Parser

---

### 3. Personal Portfolio Website

**Explanation**

Designed and developed a high-performance, fully responsive personal portfolio using Next.js 14 App Router with Client Components architecture. Implemented a modern UI using shadcn/ui, Aceternity UI, and Magic UI component libraries, styled with Tailwind CSS and deployed with Vercel.

**Technologies Used**

* React
* Next.js 14
* Shadcn UI
* Aceternity UI
* Magic UI
* Tailwind CSS
* Vercel

---

### 4. Food Ordering App MERN

**Explanation**

A full-stack food ordering application built with the MERN stack (MongoDB, Express.js, React, Node.js). The platform allows users to browse restaurants, place orders, and manage their profiles, while restaurant owners can manage menus and incoming orders.

**Technologies Used**

**Frontend**

* TypeScript
* React
* Vite
* Tailwind CSS
* Shadcn UI
* React Router
* Axios
* React Query
* Zod

**Backend**

* TypeScript
* Node.js
* Express.js
* MongoDB
* Mongoose
* JWT
* Cloudinary
* Multer
* Stripe

**Other Tools**

* Postman
* Git
* Render

---

### 5. Hotel Booking App MERN

**Explanation**

A full-stack hotel booking platform built with the MERN stack. The application allows users to browse hotels, make reservations, and manage bookings securely.

**Technologies Used**

**Frontend**

* TypeScript
* React.js
* Vite
* Tailwind CSS
* React Router
* React Hook Form
* React Query

**Backend**

* TypeScript
* Node.js
* Express.js
* MongoDB
* Mongoose
* JWT
* Cloudinary
* Stripe

**Testing**

* Playwright (End-to-End Testing)

---

### 6. NestJS Library Management

**Explanation**

A backend application built with NestJS for managing a library system. It implements real-world library rules including borrowing limits, fine calculation, and role-based access control. The system tracks books, authors, users, borrows, and fines using a PostgreSQL database and exposes RESTful APIs.

**Technologies Used**

* NestJS
* TypeScript
* TypeORM
* PostgreSQL
* JWT
* bcrypt
* class-validator
* ConfigModule
* Express
* ValidationPipe
* Guards

---

### 7. .NET Cloud File Storage Microservice

**Explanation**

A cloud file storage platform built using a microservices architecture. The system allows users to securely store, manage, and share files. Features include authentication, file uploads, downloads, file sharing options, and centralized API communication through an API Gateway.

**Technologies Used**

**Frontend**

* ASP.NET Core MVC
* HTML
* CSS
* Bootstrap

**Backend**

* .NET
* SQLite
* PostgreSQL
* MediatR
* AutoMapper
* FluentValidation
* YARP
* JWT
* bcrypt

---

### 8. NestJS English Vocabulary Trainer

**Explanation**

A backend learning platform currently under development. The application aims to help users memorize English vocabulary through exercises and learning workflows.

**Technologies Used**

* NestJS
* TypeScript
* Prisma
* PostgreSQL
* JWT
* bcrypt
* Swagger

---

### 9. AI Gift Advisor

**Explanation**

AI Gift Advisor is a full-stack web application that generates personalized gift suggestions using AI. Users describe a person or occasion, and the system produces tailored gift ideas using the OpenAI GPT-5 model.

**Technologies Used**

* Node.js
* Express.js
* OpenAI API
* Streaming Responses
* React
* Vite
* Marked (Markdown Rendering)
* DOMPurify

---

### 10. AI Knowledge Base Assistant (Full-Stack RAG Platform)

**Explanation**

A production-style Retrieval-Augmented Generation platform that turns documents (PDF, Markdown, Slack exports, wikis) into a queryable knowledge base. The ingestion pipeline cleans, chunks and embeds documents into pgvector; the query pipeline rewrites the question, retrieves the closest chunks, scores retrieval confidence, assembles a token-budgeted context and returns a grounded answer with source attribution. Built as a NestJS + Next.js monorepo with the pipeline logic implemented directly rather than delegated to a chain library.

**Technologies Used**

* NestJS
* Next.js
* TypeScript
* PostgreSQL (pgvector)
* Supabase
* OpenAI API (GPT + embeddings)
* LangChain
* Tailwind CSS
* Jest

---

### 11. Job Application Agent (AI CV Automation + LinkedIn Assistant)

**Explanation**

A Python automation platform that runs a whole job search end-to-end. A background poller watches a job-application spreadsheet, scrapes each new posting, and generates an ATS-optimized CV per job with Claude, rendering it from Markdown into a .docx template and exporting it to Google Docs and PDF. In parallel, a Chrome MV3 extension backed by a FastAPI service reads the LinkedIn posting the user is viewing and shows a short Turkish summary, the required stack, and a technology-fit score that is computed deterministically in Python instead of being left to the model. The panel can also add the job to the spreadsheet with one click and generate a cover letter on demand. Two processes share one workbook, so the writes are serialized with a cross-process file lock, and results are cached both in memory and on disk with a version stamp that invalidates them when the scoring rules change.

**Technologies Used**

**Backend**

* Python
* FastAPI
* Uvicorn
* Pydantic
* Anthropic Claude API
* Playwright
* BeautifulSoup4
* openpyxl
* python-docx
* Google Drive & Docs API
* OAuth 2.0 / Service Account
* REST API
* Prompt Engineering
* File Locking & Concurrency
* Caching (LRU + disk)

**Frontend**

* JavaScript
* Chrome Extension (Manifest V3)
* HTML
* CSS
* Shadow DOM

**Other Tools**

* Git
* Shell scripting
