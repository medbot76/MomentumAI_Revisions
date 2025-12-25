import React, { useState } from 'react'
import { API_ENDPOINTS } from '../config';
import { Link, useNavigate } from 'react-router-dom';

function Register() {
    const navigate = useNavigate();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [message, setMessage] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isSuccess, setIsSuccess] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setMessage('');
        setIsSuccess(false);
        setIsLoading(true);

        // Check if passwords match before proceeding with registration
        if (password !== confirmPassword) {
            setMessage('Passwords do not match');
            setIsLoading(false);
            return;
        }

        // Check password length
        if (password.length < 6) {
            setMessage('Password must be at least 6 characters long');
            setIsLoading(false);
            return;
        }

        try {
          const response = await fetch(API_ENDPOINTS.AUTH_SIGNUP, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            credentials: 'include', // Important for session cookies
            body: JSON.stringify({
              email,
              password,
            })
          });
          
          const data = await response.json();
          
          if (response.ok && data.user) {
            setIsSuccess(true);
            setMessage('Account created successfully! Redirecting...');
            // Redirect to home after successful registration
            setTimeout(() => {
              window.location.href = '/';
            }, 1500);
          } else {
            setMessage(data.error || 'Registration failed');
            setIsLoading(false);
          }
        } catch (error) {
          setMessage(error.message || 'An error occurred');
          setIsLoading(false);
        }
    }
        
    return (
        <div className="flex items-center justify-center min-h-screen bg-white">
            <div className="w-full max-w-md px-6 md:px-8 py-12 md:py-16 relative">
                <button
                    onClick={() => navigate('/')}
                    className="absolute top-6 right-6 text-gray-400 hover:text-gray-600 transition-colors"
                >
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
                
                <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-3 text-center">Create account</h1>
                <p className="text-lg text-gray-600 text-center mb-8">Join us and start your learning journey</p>
                
                {message && (
                    <div className={`mb-6 p-4 rounded-lg border ${
                        isSuccess 
                            ? 'bg-green-50 border-green-200' 
                            : 'bg-red-50 border-red-200'
                    }`}>
                        <p className={`text-sm text-center ${
                            isSuccess ? 'text-green-600' : 'text-red-600'
                        }`}>
                            {message}
                        </p>
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
                        placeholder="Password (min. 6 characters)" 
                        value={password} 
                        onChange={(e) => setPassword(e.target.value)} 
                        required
                        minLength={6}
                        className="w-full px-5 py-3.5 border border-gray-300 rounded-full focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-transparent transition-all bg-white placeholder-gray-500"
                    />
                    
                    <input 
                        id="confirmPassword"
                        type="password" 
                        placeholder="Confirm password" 
                        value={confirmPassword} 
                        onChange={(e) => setConfirmPassword(e.target.value)} 
                        required
                        className="w-full px-5 py-3.5 border border-gray-300 rounded-full focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-transparent transition-all bg-white placeholder-gray-500"
                    />
                    
                    <button 
                        type="submit"
                        disabled={isLoading || isSuccess}
                        className="w-full bg-black text-white hover:bg-gray-800 font-medium py-3.5 px-6 rounded-full transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed text-base"
                    >
                        {isLoading ? 'Creating account...' : isSuccess ? 'Account created!' : 'Continue'}
                    </button>
                </form>
                
                <div className="text-center">
                    <p className="text-sm text-gray-600">
                        Already have an account?{' '}
                        <Link to="/login" className="text-gray-900 hover:text-gray-700 font-semibold transition-colors">
                            Sign in
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    )
}

export default Register