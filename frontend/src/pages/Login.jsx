import React, { useState } from 'react'
import { API_ENDPOINTS } from '../config'
import { Link, useNavigate } from 'react-router-dom';

function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  const handleSubmit = async (event) => {
    event.preventDefault();
    setMessage("");
    setIsLoading(true);
    
    try {
      const response = await fetch(API_ENDPOINTS.AUTH_LOGIN, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          email: email,
          password: password,
        })
      });
      
      const data = await response.json();
      
      if (response.ok && data.user) {
        window.location.href = '/';
      } else if (data.requires_verification) {
        navigate('/verify-email', { state: { email: data.email || email } });
      } else {
        setMessage(data.error || 'Login failed');
        setIsLoading(false);
      }
    } catch (error) {
      setMessage(error.message || 'An error occurred');
      setIsLoading(false);
    }
  }
  
  return (
    <div className="flex items-center justify-center min-h-screen bg-white">
      <div className="w-full max-w-md px-6 md:px-8 py-12 md:py-16">
        <button
          onClick={() => navigate('/')}
          className="absolute top-6 right-6 text-gray-400 hover:text-gray-600 transition-colors"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
        
        <div className="mb-8">
          <img 
            src="/medbotlogonew.jpg" 
            alt="Momentum AI" 
            className="w-8 h-8 rounded-md mx-auto"
          />
        </div>
        
        <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-3 text-center">Sign in</h1>
        <p className="text-lg text-gray-600 text-center mb-8">Welcome back! Please sign in to continue.</p>
        
        {message && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-600 text-center">{message}</p>
          </div>
        )}
        
        <form onSubmit={handleSubmit} className="space-y-4 mb-6">
          <input
            id="email"
            type="email"
            placeholder="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full px-5 py-3.5 border border-gray-300 rounded-full focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-transparent transition-all bg-white placeholder-gray-500"
          />
          
          <input
            id="password"
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full px-5 py-3.5 border border-gray-300 rounded-full focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-transparent transition-all bg-white placeholder-gray-500"
          />
          
          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-black text-white hover:bg-gray-800 font-medium py-3.5 px-6 rounded-full transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed text-base"
          >
            {isLoading ? 'Signing in...' : 'Continue'}
          </button>
        </form>
        
        <div className="text-center">
          <p className="text-sm text-gray-600">
            Don't have an account?{' '}
            <Link to="/register" className="text-gray-900 hover:text-gray-700 font-semibold transition-colors">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}

export default Login