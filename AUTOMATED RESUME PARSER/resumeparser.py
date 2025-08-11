import os
import re
from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename
import PyPDF2
import docx2txt
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Create upload directory
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'resume_parser',
    'user': 'your_username',
    'password': 'your_password',
    'port': '5432'
}

class ResumeParser:
    def __init__(self):
        self.skills_keywords = [
            'python', 'java', 'javascript', 'react', 'node.js', 'sql', 'postgresql', 
            'mysql', 'mongodb', 'docker', 'kubernetes', 'aws', 'azure', 'git',
            'machine learning', 'data science', 'html', 'css', 'flask', 'django',
            'spring boot', 'microservices', 'rest api', 'graphql', 'tensorflow',
            'pytorch', 'pandas', 'numpy', 'scikit-learn', 'angular', 'vue.js'
        ]
        
    def extract_text_from_pdf(self, file_path):
        """Extract text from PDF file"""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
                return text
        except Exception as e:
            print(f"Error extracting PDF: {e}")
            return ""
    
    def extract_text_from_docx(self, file_path):
        """Extract text from DOCX file"""
        try:
            return docx2txt.process(file_path)
        except Exception as e:
            print(f"Error extracting DOCX: {e}")
            return ""
    
    def extract_name(self, text):
        """Extract candidate name from resume text using regex patterns"""
        lines = text.strip().split('\n')
        
        # Look for name patterns in first few lines
        for i, line in enumerate(lines[:5]):
            line = line.strip()
            # Skip empty lines and lines with common resume keywords
            if (line and 
                not re.search(r'(resume|cv|curriculum|vitae|phone|email|address|objective)', line.lower()) and
                not re.search(r'^\d+', line) and  # Skip lines starting with numbers
                len(line.split()) <= 4 and  # Names usually 1-4 words
                len(line) > 2):
                
                # Check if it looks like a name (contains letters, maybe spaces)
                if re.match(r'^[A-Za-z\s\.\-\']+$', line):
                    return line.title()
        
        return "Name not found"
    
    def extract_email(self, text):
        """Extract email address from resume text"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        return emails[0] if emails else "Email not found"
    
    def extract_phone(self, text):
        """Extract phone number from resume text"""
        # Multiple phone patterns
        phone_patterns = [
            r'(\+\d{1,3}[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})',
            r'(\+\d{1,3}[-.\s]?)?(\d{3})[-.\s]?(\d{3})[-.\s]?(\d{4})',
            r'(\+\d{1,3}[-.\s]?)?\d{10}'
        ]
        
        for pattern in phone_patterns:
            phones = re.findall(pattern, text)
            if phones:
                if isinstance(phones[0], tuple):
                    return ''.join(phones[0])
                else:
                    return phones[0]
        
        return "Phone not found"
    
    def extract_skills(self, text):
        """Extract skills from resume text"""
        text_lower = text.lower()
        found_skills = []
        
        for skill in self.skills_keywords:
            if skill.lower() in text_lower:
                found_skills.append(skill.title())
        
        return found_skills
    
    def extract_education(self, text):
        """Extract education information from resume text"""
        education_keywords = [
            'bachelor', 'master', 'phd', 'doctorate', 'degree',
            'university', 'college', 'institute', 'school',
            'b.s.', 'b.a.', 'm.s.', 'm.a.', 'mba', 'ph.d.',
            'b.tech', 'm.tech', 'be', 'me'
        ]
        
        education_info = []
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in education_keywords):
                # Get this line and potentially the next one for context
                edu_text = line.strip()
                if i + 1 < len(lines) and len(lines[i + 1].strip()) > 0:
                    edu_text += " " + lines[i + 1].strip()
                if edu_text:
                    education_info.append(edu_text)
        
        return education_info[:3]  # Return top 3 education entries
    
    def extract_experience(self, text):
        """Extract work experience from resume text"""
        # Look for year patterns (e.g., 2020-2023, 2019-Present)
        year_patterns = [
            r'(20\d{2})\s*[-–]\s*(20\d{2}|present|current)',
            r'(19\d{2})\s*[-–]\s*(20\d{2}|present|current)',
            r'(20\d{2})\s*[-–]\s*(20\d{2})',
        ]
        
        experience_years = 0
        for pattern in year_patterns:
            years = re.findall(pattern, text, re.IGNORECASE)
            experience_years += len(years)
        
        # Also look for experience keywords
        exp_keywords = ['years of experience', 'years experience', 'experience:', 'work experience']
        exp_mentions = sum(1 for keyword in exp_keywords if keyword.lower() in text.lower())
        
        total_indicators = experience_years + exp_mentions
        
        if total_indicators > 0:
            return f"Approximately {total_indicators} experience indicators found"
        else:
            return "Experience details not clearly identified"
    
    def parse_resume(self, file_path, filename):
        """Main method to parse resume and extract all information"""
        # Extract text based on file type
        if filename.lower().endswith('.pdf'):
            text = self.extract_text_from_pdf(file_path)
        elif filename.lower().endswith('.docx'):
            text = self.extract_text_from_docx(file_path)
        else:
            return {"error": "Unsupported file format"}
        
        if not text.strip():
            return {"error": "Could not extract text from file"}
        
        # Extract information
        parsed_data = {
            'filename': filename,
            'name': self.extract_name(text),
            'email': self.extract_email(text),
            'phone': self.extract_phone(text),
            'skills': self.extract_skills(text),
            'education': self.extract_education(text),
            'experience': self.extract_experience(text),
            'raw_text': text[:1000] + "..." if len(text) > 1000 else text,
            'parsed_date': datetime.now().isoformat()
        }
        
        return parsed_data

class DatabaseManager:
    def __init__(self):  # Fixed: __init__ instead of _init_
        self.create_table()
    
    def get_connection(self):
        """Create database connection with better error handling"""
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            return conn
        except psycopg2.OperationalError as e:
            print(f"Database connection error: {e}")
            print("Make sure PostgreSQL is running and database credentials are correct")
            return None
        except Exception as e:
            print(f"Unexpected database error: {e}")
            return None
    
    def create_table(self):
        """Create candidates table if it doesn't exist"""
        conn = self.get_connection()
        if not conn:
            print("Skipping table creation due to database connection issues")
            return
        
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS candidates (
                    id SERIAL PRIMARY KEY,
                    filename VARCHAR(255),
                    name VARCHAR(255),
                    email VARCHAR(255),
                    phone VARCHAR(50),
                    skills TEXT[],
                    education TEXT[],
                    experience TEXT,
                    raw_text TEXT,
                    parsed_date TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            print("Database table created successfully")
        except Exception as e:
            print(f"Error creating table: {e}")
        finally:
            conn.close()
    
    def save_candidate(self, data):
        """Save candidate data to database"""
        conn = self.get_connection()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO candidates (filename, name, email, phone, skills, education, experience, raw_text, parsed_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                data['filename'],
                data['name'],
                data['email'],
                data['phone'],
                data['skills'],
                data['education'],
                data['experience'],
                data['raw_text'],
                data['parsed_date']
            ))
            candidate_id = cursor.fetchone()[0]
            conn.commit()
            return candidate_id
        except Exception as e:
            print(f"Error saving candidate: {e}")
            return False
        finally:
            conn.close()
    
    def search_candidates(self, query):
        """Search candidates in database"""
        conn = self.get_connection()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT * FROM candidates 
                WHERE name ILIKE %s 
                OR email ILIKE %s 
                OR %s = ANY(skills)
                OR raw_text ILIKE %s
                ORDER BY created_at DESC
            ''', (f'%{query}%', f'%{query}%', query, f'%{query}%'))
            
            results = cursor.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            print(f"Error searching candidates: {e}")
            return []
        finally:
            conn.close()

# Initialize components
parser = ResumeParser()
db = DatabaseManager()

# HTML template for the web interface
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Resume Parser</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .upload-form { border: 2px dashed #ccc; padding: 20px; margin: 20px 0; text-align: center; }
        .search-form { margin: 20px 0; }
        .result { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .skills { display: flex; flex-wrap: wrap; gap: 5px; }
        .skill-tag { background: #007bff; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }
        input[type="file"], input[type="text"] { margin: 10px; padding: 8px; }
        button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .error { color: red; }
        .success { color: green; }
    </style>
</head>
<body>
    <h1>Automated Resume Parser</h1>
    
    <div class="upload-form">
        <h3>Upload Resume</h3>
        <form id="uploadForm" enctype="multipart/form-data">
            <input type="file" name="resume" accept=".pdf,.docx" required>
            <button type="submit">Parse Resume</button>
        </form>
        <div id="uploadResult"></div>
    </div>
    
    <div class="search-form">
        <h3>Search Candidates</h3>
        <form id="searchForm">
            <input type="text" name="query" placeholder="Search by name, email, skills, or keywords">
            <button type="submit">Search</button>
        </form>
        <div id="searchResults"></div>
    </div>

    <script>
        document.getElementById('uploadForm').onsubmit = function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                const resultDiv = document.getElementById('uploadResult');
                if (data.error) {
                    resultDiv.innerHTML = '<div class="error">Error: ' + data.error + '</div>';
                } else {
                    resultDiv.innerHTML = `
                        <div class="success">Resume parsed successfully!</div>
                        <div class="result">
                            <h4>${data.name}</h4>
                            <p><strong>Email:</strong> ${data.email}</p>
                            <p><strong>Phone:</strong> ${data.phone}</p>
                            <p><strong>Skills:</strong></p>
                            <div class="skills">
                                ${data.skills.map(skill => '<span class="skill-tag">' + skill + '</span>').join('')}
                            </div>
                            <p><strong>Education:</strong></p>
                            <ul>${data.education.map(edu => '<li>' + edu + '</li>').join('')}</ul>
                            <p><strong>Experience:</strong> ${data.experience}</p>
                        </div>
                    `;
                }
            })
            .catch(error => {
                document.getElementById('uploadResult').innerHTML = '<div class="error">Error: ' + error + '</div>';
            });
        };

        document.getElementById('searchForm').onsubmit = function(e) {
            e.preventDefault();
            const query = this.query.value;
            
            fetch('/search?q=' + encodeURIComponent(query))
            .then(response => response.json())
            .then(data => {
                const resultsDiv = document.getElementById('searchResults');
                if (data.length === 0) {
                    resultsDiv.innerHTML = '<p>No candidates found.</p>';
                } else {
                    resultsDiv.innerHTML = '<h4>Search Results:</h4>' + 
                        data.map(candidate => `
                            <div class="result">
                                <h5>${candidate.name}</h5>
                                <p><strong>Email:</strong> ${candidate.email}</p>
                                <p><strong>Phone:</strong> ${candidate.phone}</p>
                                <div class="skills">
                                    ${candidate.skills ? candidate.skills.map(skill => '<span class="skill-tag">' + skill + '</span>').join('') : ''}
                                </div>
                                <p><strong>Uploaded:</strong> ${new Date(candidate.created_at).toLocaleDateString()}</p>
                            </div>
                        `).join('');
                }
            });
        };
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """Main page"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload_resume():
    """Handle resume upload and parsing"""
    if 'resume' not in request.files:
        return jsonify({'error': 'No file uploaded'})
    
    file = request.files['resume']
    if file.filename == '':
        return jsonify({'error': 'No file selected'})
    
    if file and file.filename.lower().endswith(('.pdf', '.docx')):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Parse the resume
        parsed_data = parser.parse_resume(file_path, filename)
        
        if 'error' in parsed_data:
            return jsonify(parsed_data)
        
        # Save to database
        candidate_id = db.save_candidate(parsed_data)
        if candidate_id:
            parsed_data['id'] = candidate_id
            parsed_data['status'] = 'saved'
        else:
            parsed_data['status'] = 'parsed but not saved to database'
        
        # Clean up uploaded file
        try:
            os.remove(file_path)
        except:
            pass  # File cleanup is not critical
        
        return jsonify(parsed_data)
    
    return jsonify({'error': 'Invalid file format. Please upload PDF or DOCX files.'})

@app.route('/search')
def search_candidates():
    """Search candidates in database"""
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    
    results = db.search_candidates(query)
    return jsonify(results)

@app.route('/api/candidates')
def get_all_candidates():
    """Get all candidates from database"""
    conn = db.get_connection()
    if not conn:
        return jsonify([])
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT * FROM candidates ORDER BY created_at DESC')
        results = cursor.fetchall()
        return jsonify([dict(row) for row in results])
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        conn.close()

if __name__ == '__main__':  # Fixed: __name__ instead of _name_
    print("Starting Resume Parser Application...")
    print("Make sure to:")
    print("1. Install required packages: pip install flask PyPDF2 python-docx psycopg2-binary spacy")
    print("2. Download spaCy model: python -m spacy download en_core_web_sm")
    print("3. Set up PostgreSQL database and update DB_CONFIG")
    print("4. Create database: CREATE DATABASE resume_parser;")
    
    app.run(debug=True, port=5000)