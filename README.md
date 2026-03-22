# Nigerian Army E-Library System

A comprehensive digital library management system for the Nigerian Army, featuring book management, user authentication, circulation control, and advanced reading analytics.

## 📚 Overview

The Nigerian Army E-Library is a full-featured digital library management system designed to serve military personnel and civilians. It provides access to military publications, strategic documents, training materials, and general literature with role-based access control and security clearance levels.

## ✨ Features

### 👤 User Management
- **Civilian Registration** - Standard patrons with basic access
- **Military OAuth Login** - Integration with Nigerian Army authentication portal
- **Role-Based Access** - Admin, Librarian, Cataloger, and User roles
- **Security Clearance Levels** - Basic, Confidential, Secret, Top Secret
- **Profile Management** - Profile pictures, personal details, and preferences
- **Email & WhatsApp Notifications** - Real-time alerts for approvals and updates

### 📖 Book Management
- **Digital & Physical Books** - Support for both formats
- **Advanced Search** - Search by title, author, category, and tags
- **Categories & Tags** - Dynamic category and tag management
- **Featured Books** - Highlight important publications
- **New Arrivals** - Track recently added books
- **Bestsellers** - Most popular books by downloads
- **Recommended Books** - AI-powered recommendations

### 🔄 Circulation Management
- **Borrowing System** - Track book loans with due dates
- **Renewals** - Allow users to renew borrowed books
- **Reservations** - Hold system for unavailable books
- **Fine Management** - Automated fine calculation for overdue items
- **Check-in/Check-out** - Barcode scanning support

### 📊 Reading Analytics
- **Reading Progress** - Track user reading progress
- **Bookmarks & Annotations** - Save reading positions and notes
- **Reading History** - Complete user reading history
- **Download Statistics** - Track popular downloads
- **User Activity** - Monitor user engagement

### 👨‍💼 Admin Features
- **User Approval Workflow** - Approve/reject new registrations
- **Book Upload** - Upload books with covers and metadata
- **Cataloging Queue** - Manage cataloging tasks
- **Acquisition Requests** - Handle book purchase requests
- **Purchase Orders** - Create and manage vendor orders
- **Reports** - Generate circulation, acquisition, and usage reports
- **System Settings** - Configure library settings
- **Audit Logs** - Track all administrative actions

### 🔒 Security Features
- **CSRF Protection** - Secure form submissions
- **Rate Limiting** - Prevent abuse
- **Session Management** - Secure session handling
- **Password Hashing** - Secure password storage
- **Two-Factor Authentication** - Optional 2FA for admin accounts
- **Security Clearance** - Access control for restricted materials

### 📱 Notifications
- **Email Notifications** - Approval, rejection, due date reminders
- **WhatsApp Notifications** - Instant alerts via Twilio
- **SMS Notifications** - Africa's Talking integration
- **In-App Notifications** - Dashboard alerts

### 🔧 Technical Features
- **RESTful API** - Comprehensive API for external integrations
- **Solr Search** - High-performance full-text search
- **Redis Caching** - Optimize performance
- **Celery Tasks** - Asynchronous background jobs
- **Database Backups** - Automated backup system
- **Scheduled Reports** - Automated report generation

## 🚀 Technology Stack

### Backend
- **Python 3.11+** - Core language
- **Flask** - Web framework
- **SQLAlchemy** - ORM
- **PostgreSQL** - Primary database
- **Redis** - Caching and task queue
- **Celery** - Background tasks
- **Gunicorn** - WSGI server

### Frontend
- **HTML5/CSS3** - Structure and styling
- **Tailwind CSS** - Utility-first CSS framework
- **JavaScript** - Interactive features
- **Alpine.js** - Lightweight JavaScript framework
- **Font Awesome** - Icons

### External Services
- **Twilio** - WhatsApp notifications
- **Africa's Talking** - SMS notifications
- **Sentry** - Error tracking
- **Solr** - Search engine
- **AWS S3** - Cloud backups

## 📋 Prerequisites

### System Requirements
- **Operating System**: Ubuntu 20.04/22.04 LTS (recommended)
- **CPU**: 2+ cores
- **RAM**: 2GB minimum (4GB recommended)
- **Storage**: 20GB minimum
- **Python**: 3.11+
- **PostgreSQL**: 14+
- **Redis**: 6+

### Software Dependencies
```bash
# System packages
sudo apt update
sudo apt install -y python3.11 python3-pip python3-venv python3-dev
sudo apt install -y postgresql postgresql-contrib redis-server nginx supervisor
sudo apt install -y build-essential libssl-dev libffi-dev