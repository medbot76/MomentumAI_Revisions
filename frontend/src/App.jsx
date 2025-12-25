"use client"

import React from 'react';
import './App.css';
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import Home from './pages/Home';
import Wrapper from './pages/Wrapper';
import Login from './pages/Login';
import Register from './pages/Register';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route 
          path="/*" 
          element={
            <Wrapper>
              <Home />
            </Wrapper>    
          } 
        />
      </Routes>
    </Router>
  );
}

export default App;