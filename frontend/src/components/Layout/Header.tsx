import React from 'react';
import { useNavigate } from 'react-router-dom';
import styles from './Header.module.css';

interface HeaderProps {
  username?: string;
}

export const Header: React.FC<HeaderProps> = () => {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    navigate('/login');
  };

  return (
    <header className={styles.header}>
      <span className={styles.brand}>PROJECT_DIPLOM</span>
      <button className={styles.userBtn} onClick={handleLogout}>
        Выход
      </button>
    </header>
  );
};
