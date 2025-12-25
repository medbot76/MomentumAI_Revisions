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
        <div className="flex items-center justify-center min-h-screen bg-gray-50">
            <div className="w-full max-w-md mx-4">
                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-10 md:p-12">
                    {/* Logo */}
                    <div className="flex items-center gap-3 mb-8">
                        <img 
                            src="/medbotlogonew.jpg" 
                            alt="Momentum AI Logo" 
                            className="w-10 h-10 rounded-xl object-cover"
                        />
                        <span className="font-semibold text-2xl text-gray-900">Momentum AI</span>
                    </div>
                    
                    <h1 className="text-3xl font-semibold text-gray-900 mb-2 text-center">Create Account</h1>
                    <p className="text-gray-600 text-center mb-8">Join MedBot and start your learning journey</p>
                    
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
                    
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <input 
                                id="email"
                                type="email" 
                                placeholder="you@example.com" 
                                value={email} 
                                onChange={(e) => setEmail(e.target.value)} 
                                required
                                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-transparent transition-all bg-white"
                            />
                        </div>
                        
                        <div>
                            <input 
                                id="password"
                                type="password" 
                                placeholder="password (min. 6 characters)" 
                                value={password} 
                                onChange={(e) => setPassword(e.target.value)} 
                                required
                                minLength={6}
                                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-transparent transition-all bg-white"
                            />
                        </div>
                        
                        <div>
                            <input 
                                id="confirmPassword"
                                type="password" 
                                placeholder="confirm password" 
                                value={confirmPassword} 
                                onChange={(e) => setConfirmPassword(e.target.value)} 
                                required
                                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-transparent transition-all bg-white"
                            />
                        </div>
                        
                        <button 
                            type="submit"
                            disabled={isLoading || isSuccess}
                            className="w-full bg-black text-white hover:bg-gray-800 font-medium py-3.5 px-6 rounded-xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {isLoading ? 'Creating Account...' : isSuccess ? 'Account Created!' : 'Create Account'}
                        </button>
                    </form>
                    
                    <div className="mt-6 text-center">
                        <p className="text-sm text-gray-600">
                            Already have an account?{' '}
                            <Link to="/login" className="text-gray-900 hover:text-gray-700 font-medium transition-colors">
                                Sign In
                            </Link>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default Register