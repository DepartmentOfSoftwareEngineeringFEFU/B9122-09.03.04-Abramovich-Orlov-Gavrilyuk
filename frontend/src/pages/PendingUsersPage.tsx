import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldAlert, Clock, User, Check, Ban, CheckCircle2 } from 'lucide-react';
import { authApi } from '../api/apiService';
import styles from './PendingUsersPage.module.css';

interface User {
  id: number;
  username: string;
  email: string | null;
  full_name: string;
  date_joined: string;
  is_active: boolean;
}

interface UserWithStatus extends User {
  status: 'pending' | 'approved' | 'rejected';
  canApproveUsers?: boolean;
}

export const PendingUsersPage: React.FC = () => {
  const [users, setUsers] = useState<UserWithStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const navigate = useNavigate();

  const ITEMS_PER_PAGE = 5;

  useEffect(() => {
    fetchPendingUsers();
  }, []);

  const showToast = (message: string) => {
    setToastMessage(message);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const fetchPendingUsers = async () => {
    try {
      const data = await authApi.getPendingUsers();
      setUsers(data.map((u: User) => ({ ...u, status: 'pending' as const, canApproveUsers: false })));
    } catch (err) {
      console.error('Fetch error:', err);
      setError(err instanceof Error ? err.message : 'Ошибка загрузки списка пользователей');
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (userId: number, action: 'approved' | 'rejected', canApproveUsers = false) => {
    try {
      if (action === 'approved') {
        await authApi.approveUser(userId, canApproveUsers);
        showToast(`Пользователь REQ-${userId} успешно подтвержден`);
      } else {
        await authApi.rejectUser(userId);
        showToast(`Заявка REQ-${userId} отклонена`);
      }

      // Update status for animation
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, status: action } : u));

      // Remove from list after animation
      setTimeout(() => {
        setUsers(prev => prev.filter(u => u.id !== userId));
      }, 500);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Ошибка выполнения действия');
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const pendingCount = users.filter(u => u.status === 'pending').length;

  // Pagination
  const totalPages = Math.ceil(users.length / ITEMS_PER_PAGE);
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const endIndex = startIndex + ITEMS_PER_PAGE;
  const currentUsers = users.slice(startIndex, endIndex);
  const showPagination = users.length > ITEMS_PER_PAGE;

  // Reset to page 1 when users list changes
  React.useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) {
      setCurrentPage(totalPages);
    }
  }, [users.length, currentPage, totalPages]);

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>Загрузка...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>{error}</div>
        <button onClick={() => navigate('/admin')} className={styles.backButton}>
          Вернуться на главную
        </button>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {/* Header with counter */}
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Запросы на регистрацию</h1>
          <p className={styles.subtitle}>
            <ShieldAlert size={16} className={styles.alertIcon} />
            Требуется проверка администратором
          </p>
        </div>
        <div className={styles.counter}>
          ОЖИДАЮТ: {pendingCount}
        </div>
      </div>

      {/* User cards */}
      <div className={styles.cardList}>
        {users.length === 0 ? (
          <div className={styles.emptyState}>
            <CheckCircle2 size={64} className={styles.emptyIcon} strokeWidth={1} />
            <h3 className={styles.emptyTitle}>Все заявки обработаны</h3>
            <p className={styles.emptyText}>Новых запросов на регистрацию нет.</p>
          </div>
        ) : (
          currentUsers.map((user) => (
            <div
              key={user.id}
              className={`${styles.card} ${
                user.status === 'approved' ? styles.cardApproved : ''
              } ${user.status === 'rejected' ? styles.cardRejected : ''}`}
            >
              <div className={styles.cardAccent} />

              <div className={styles.cardContent}>
                <div className={styles.cardMeta}>
                  <span className={styles.cardId}>REQ-{user.id}</span>
                  <span className={styles.cardDate}>
                    <Clock size={12} className={styles.clockIcon} />
                    {formatDate(user.date_joined)}
                  </span>
                </div>

                <h3 className={styles.cardName}>
                  <User size={20} className={styles.userIcon} />
                  <span>{user.full_name}</span>
                </h3>

                <div className={styles.cardInfo}>
                  <p className={styles.cardInfoItem}>
                    <span className={styles.cardLabel}>EMAIL:</span> {user.email || 'Не указан'}
                  </p>

                  {/* Custom checkbox */}
                  <label className={styles.checkboxLabel}>
                    <input
                      type="checkbox"
                      checked={user.canApproveUsers || false}
                      onChange={(e) => {
                        setUsers(prev => prev.map(u =>
                          u.id === user.id ? { ...u, canApproveUsers: e.target.checked } : u
                        ));
                      }}
                      disabled={user.status !== 'pending'}
                      className={styles.checkboxInput}
                    />
                    <div className={styles.checkboxCustom}>
                      {user.canApproveUsers && <Check size={14} strokeWidth={3} />}
                    </div>
                    <span className={styles.checkboxText}>Дать право подтверждать учётные записи</span>
                  </label>
                </div>
              </div>

              <div className={styles.cardActions}>
                <button
                  onClick={() => handleAction(user.id, 'rejected')}
                  className={styles.btnReject}
                  disabled={user.status !== 'pending'}
                >
                  <Ban size={16} />
                  Отклонить
                </button>
                <button
                  onClick={() => handleAction(user.id, 'approved', user.canApproveUsers)}
                  className={styles.btnApprove}
                  disabled={user.status !== 'pending'}
                >
                  <Check size={18} />
                  Подтвердить
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {showPagination && (
        <div className={styles.pagination}>
          <button
            onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
            disabled={currentPage === 1}
            className={styles.paginationBtn}
          >
            ← Назад
          </button>
          <span className={styles.paginationInfo}>
            Страница {currentPage} из {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
            disabled={currentPage === totalPages}
            className={styles.paginationBtn}
          >
            Вперёд →
          </button>
        </div>
      )}

      {/* Toast notification */}
      {toastMessage && (
        <div className={styles.toast}>
          <div className={styles.toastDot} />
          SYS.MSG // {toastMessage}
        </div>
      )}
    </div>
  );
};
