import React from 'react';
import './../assets/styles/Footer.css';

export default function Footer() {
  return (
    <footer className="app-footer">
      <div className="footer-inner">
        <div className="footer-left">
          <span>AGH University of Science and Technology</span>
        </div>
        <ul className="footer-links">
          <li>
            <a href="https://github.com/your-repository" target="_blank" rel="noopener noreferrer">
              Repository
            </a>
          </li>
          <li>
            <a href="https://github.com/your-repository" target="_blank" rel="noopener noreferrer">
              Documentation
            </a>
          </li>
        </ul>
      </div>
    </footer>
  );
}
