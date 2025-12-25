import React, { useState, useEffect, useRef } from 'react'
import { API_ENDPOINTS } from '../config';
import { Link, useNavigate, useLocation } from 'react-router-dom';

function VerifyEmail() {
    const navigate = useNavigate();
    const location = useLocation();
    const email = location.state?.email || '';
    
    const [code, setCode] = useState(['', '', '', '', '', '']);
    const [message, setMessage] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isSuccess, setIsSuccess] = useState(false);
    const [cooldown, setCooldown] = useState(0);
    
    const inputRefs = useRef([]);
    
    useEffect(() => {
        if (!email) {
            navigate('/register');
        }
    }, [email, navigate]);
    
    useEffect(() => {
        if (cooldown > 0) {
            const timer = setTimeout(() => setCooldown(cooldown - 1), 1000);
            return () => clearTimeout(timer);
        }
    }, [cooldown]);
    
    const handleCodeChange = (index, value) => {
        if (!/^\d*$/.test(value)) return;
        
        const newCode = [...code];
        newCode[index] = value.slice(-1);
        setCode(newCode);
        
        if (value && index < 5) {
            inputRefs.current[index + 1]?.focus();
        }
        
        if (newCode.every(digit => digit !== '') && newCode.join('').length === 6) {
            handleSubmit(null, newCode.join(''));
        }
    };
    
    const handleKeyDown = (index, e) => {
        if (e.key === 'Backspace' && !code[index] && index > 0) {
            inputRefs.current[index - 1]?.focus();
        }
    };
    
    const handlePaste = (e) => {
        e.preventDefault();
        const pastedData = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
        if (pastedData.length === 6) {
            const newCode = pastedData.split('');
            setCode(newCode);
            handleSubmit(null, pastedData);
        }
    };
    
    const handleSubmit = async (e, submittedCode = null) => {
        if (e) e.preventDefault();
        const verificationCode = submittedCode || code.join('');
        
        if (verificationCode.length !== 6) {
            setMessage('Please enter the 6-digit code');
            return;
        }
        
        setMessage('');
        setIsLoading(true);
        
        try {
            const response = await fetch(API_ENDPOINTS.AUTH_VERIFY_EMAIL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({
                    email,
                    code: verificationCode,
                })
            });
            
            const data = await response.json();
            
            if (response.ok && data.user) {
                setIsSuccess(true);
                setMessage('Email verified successfully! Redirecting...');
                setTimeout(() => {
                    window.location.href = '/';
                }, 1500);
            } else {
                setMessage(data.error || 'Verification failed');
                setIsLoading(false);
                setCode(['', '', '', '', '', '']);
                inputRefs.current[0]?.focus();
            }
        } catch (error) {
            setMessage(error.message || 'An error occurred');
            setIsLoading(false);
        }
    };
    
    const handleResend = async () => {
        if (cooldown > 0) return;
        
        setMessage('');
        
        try {
            const response = await fetch(API_ENDPOINTS.AUTH_RESEND_VERIFICATION, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({ email })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                setMessage('New code sent! Check your email.');
                setCooldown(60);
            } else {
                if (data.cooldown) {
                    setCooldown(data.cooldown);
                }
                setMessage(data.error || 'Failed to resend code');
            }
        } catch (error) {
            setMessage(error.message || 'An error occurred');
        }
    };
    
    return (
        <div className="flex items-center justify-center min-h-screen bg-white">
            <div className="w-full max-w-md px-6 md:px-8 py-12 md:py-16 relative">
                <button
                    onClick={() => navigate('/login')}
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
                
                <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-3 text-center">Verify your email</h1>
                <p className="text-lg text-gray-600 text-center mb-2">We sent a 6-digit code to</p>
                <p className="text-lg font-medium text-gray-900 text-center mb-8">{email}</p>
                
                {message && (
                    <div className={`mb-6 p-4 rounded-lg border ${
                        isSuccess 
                            ? 'bg-green-50 border-green-200' 
                            : message.includes('sent') 
                                ? 'bg-blue-50 border-blue-200'
                                : 'bg-red-50 border-red-200'
                    }`}>
                        <p className={`text-sm text-center ${
                            isSuccess 
                                ? 'text-green-600' 
                                : message.includes('sent')
                                    ? 'text-blue-600'
                                    : 'text-red-600'
                        }`}>
                            {message}
                        </p>
                    </div>
                )}
                
                <form onSubmit={handleSubmit} className="mb-6">
                    <div className="flex justify-center gap-2 mb-6" onPaste={handlePaste}>
                        {code.map((digit, index) => (
                            <input
                                key={index}
                                ref={(el) => (inputRefs.current[index] = el)}
                                type="text"
                                inputMode="numeric"
                                maxLength={1}
                                value={digit}
                                onChange={(e) => handleCodeChange(index, e.target.value)}
                                onKeyDown={(e) => handleKeyDown(index, e)}
                                disabled={isLoading || isSuccess}
                                className="w-12 h-14 text-center text-2xl font-bold border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-transparent transition-all disabled:opacity-50"
                            />
                        ))}
                    </div>
                    
                    <button 
                        type="submit"
                        disabled={isLoading || isSuccess || code.some(d => !d)}
                        className="w-full bg-black text-white hover:bg-gray-800 font-medium py-3.5 px-6 rounded-full transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed text-base"
                    >
                        {isLoading ? 'Verifying...' : isSuccess ? 'Verified!' : 'Verify Email'}
                    </button>
                </form>
                
                <div className="text-center space-y-4">
                    <p className="text-sm text-gray-600">
                        Didn't receive the code?{' '}
                        <button
                            onClick={handleResend}
                            disabled={cooldown > 0}
                            className={`font-semibold transition-colors ${
                                cooldown > 0 
                                    ? 'text-gray-400 cursor-not-allowed' 
                                    : 'text-gray-900 hover:text-gray-700'
                            }`}
                        >
                            {cooldown > 0 ? `Resend in ${cooldown}s` : 'Resend code'}
                        </button>
                    </p>
                    
                    <p className="text-sm text-gray-600">
                        <Link to="/register" className="text-gray-900 hover:text-gray-700 font-semibold transition-colors">
                            Use a different email
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
}

export default VerifyEmail
