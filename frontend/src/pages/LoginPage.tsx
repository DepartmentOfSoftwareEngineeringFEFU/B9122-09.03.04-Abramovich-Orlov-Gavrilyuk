import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout, ArrowLeft } from 'lucide-react';
import { authApi } from '../api/apiService';
import styles from './LoginPage.module.css';

interface LoginResponse {
  auth_token: string;
}

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) {
      setError('Заполните все поля');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const result = await authApi.login(username, password);
      const data = result as LoginResponse;
      localStorage.setItem('auth_token', data.auth_token);
      navigate('/admin');
    } catch {
      setError('Неверный логин или пароль');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={styles.page}>
      {/* Left: orange panel */}
      <div className={styles.left}>
        <div className={styles.leftPattern} />
        <div className={styles.leftDividerH} />
        <div className={styles.leftDividerV} />
        <div className={styles.leftContent}>
          <Layout size={120} strokeWidth={1} className={styles.leftIcon} />
          <p className={styles.leftLabel}>Auth_Module</p>
        </div>
      </div>

      {/* Right: form */}
      <div className={styles.right}>
        <button className={styles.backBtn} onClick={() => navigate('/')} type="button">
          <ArrowLeft size={24} />
        </button>

        <form className={styles.form} onSubmit={handleSubmit} noValidate>
          <h1 className={styles.title}>Вход в систему</h1>

          <div className={styles.fields}>
            <input
              type="text"
              className={`${styles.input} ${error ? styles.inputError : ''}`}
              placeholder="Логин"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
              autoComplete="username"
            />
            <input
              type="password"
              className={`${styles.input} ${error ? styles.inputError : ''}`}
              placeholder="Пароль"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              autoComplete="current-password"
            />
          </div>

          {error && <p className={styles.error}>{error}</p>}

          <button type="submit" className={styles.submitBtn} disabled={isLoading}>
            {isLoading ? 'Загрузка...' : 'Войти'}
          </button>

          <div className={styles.links}>
            <button
              type="button"
              className={styles.link}
              onClick={() => navigate('/register')}
            >
              Зарегистрироваться
            </button>
            <button
              type="button"
              className={styles.link}
              onClick={() => navigate('/forgot-password')}
            >
              Забыли пароль?
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;
