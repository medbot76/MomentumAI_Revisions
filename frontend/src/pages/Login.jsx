import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';

const Camera = ({ className = "w-8 h-8" }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
);

function Login() {
  const navigate = useNavigate();
  const [checking, setChecking] = useState(true);
  const [message, setMessage] = useState('');
    
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const response = await fetch(API_ENDPOINTS.AUTH_USER, {
          credentials: 'include'
        });
        const data = await response.json();
        
        if (data.authenticated) {
          navigate("/");
          return;
        }
      } catch (error) {
        console.error('Auth check failed:', error);
      }
      setChecking(false);
    };

    checkAuth();
  }, [navigate]);

  const handleLogin = () => {
    setMessage('Redirecting to login...');
    window.location.href = API_ENDPOINTS.AUTH_LOGIN;
  };

  if (checking) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div>Loading...</div>
      </div>
    );
  }
    
  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="w-full max-w-sm bg-white rounded-xl shadow p-8 flex flex-col items-center border border-gray-200">
        <div className="flex items-center justify-center w-14 h-14 bg-blue-600 text-white rounded-lg mb-4">
          <Camera className="w-8 h-8" />
        </div>
        <h1 className="text-2xl font-semibold text-gray-900 mb-2">Sign in</h1>
        <p className="text-sm text-gray-500 mb-6">Welcome! Click below to sign in with your account.</p>
        {message && <span className="text-sm text-blue-600 mb-4">{message}</span>}
        <button
          onClick={handleLogin}
          className="w-full mt-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-lg transition-colors"
        >
          Sign In
        </button>
        <p className="mt-4 text-sm text-gray-500">
          Sign in with Google, GitHub, Apple, or email
        </p>
      </div>
    </div>
  )
}

export default Login
