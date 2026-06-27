import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import { useRouteBuildings, type RouteBuilding } from '../hooks/useRouteBuildings';
import styles from './PublicHomePage.module.css';

const getPluralFloors = (count: number): string => {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod100 >= 11 && mod100 <= 19) return `${count} этажей`;
  if (mod10 === 1) return `${count} этаж`;
  if (mod10 >= 2 && mod10 <= 4) return `${count} этажа`;
  return `${count} этажей`;
};

const ParticleBackground: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    const particles: { x: number; y: number; vx: number; vy: number; size: number }[] = [];

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    window.addEventListener('resize', resize);
    resize();

    for (let i = 0; i < 70; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 1,
        vy: (Math.random() - 0.5) * 1,
        size: Math.random() * 2 + 1,
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#FF4500';

      particles.forEach((p, index) => {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();

        for (let j = index + 1; j < particles.length; j++) {
          const p2 = particles[j];
          const dx = p.x - p2.x;
          const dy = p.y - p2.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120) {
            ctx.beginPath();
            ctx.strokeStyle = `rgba(255, 69, 0, ${1 - dist / 120})`;
            ctx.lineWidth = 0.5;
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
            if (Math.random() > 0.995) {
              ctx.strokeRect(p.x - 10, p.y - 10, 20, 20);
            }
          }
        }
      });

      animationFrameId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return <canvas ref={canvasRef} className={styles.particles} />;
};

export const PublicHomePage: React.FC = () => {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [isFocused, setIsFocused] = useState(false);

  // Same source the /3d-routes picker uses, so the dropdown mirrors that screen.
  const { buildings, isLoading, error } = useRouteBuildings('public');

  const trimmed = query.trim().toLowerCase();
  const matches = trimmed
    ? buildings.filter(
        (b) =>
          b.name.toLowerCase().includes(trimmed) ||
          b.code.toLowerCase().includes(trimmed),
      )
    : buildings;

  // Deep-link straight into the corpus 3D view; the page pre-selects it on load.
  const openBuilding = (building: RouteBuilding): void => {
    navigate('/3d-routes', { state: { buildingId: building.id } });
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>SUPER_DIPLOM</div>
        <button className={styles.adminBtn} onClick={() => navigate('/login')}>
          Войти как администратор
        </button>
      </header>

      <ParticleBackground />

      <main className={styles.main}>
        <h1 className={styles.title}>Введите название или код</h1>

        <div className={styles.searchWrap}>
          <input
            className={`${styles.searchInput} ${isFocused ? styles.searchInputFocused : ''}`}
            type="text"
            placeholder="// search_query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setTimeout(() => setIsFocused(false), 200)}
          />
          <button className={`${styles.searchBtn} ${isFocused ? styles.searchBtnFocused : ''}`}>
            <Search size={28} />
          </button>

          {isFocused && (
            <div className={styles.dropdown}>
              {isLoading && (
                <div className={`${styles.dropdownItem} ${styles.dropdownItemDisabled}`}>
                  <div className={styles.dropdownItemInfo}>
                    <span className={styles.dropdownItemName}>Загрузка корпусов…</span>
                  </div>
                </div>
              )}

              {!isLoading && error && (
                <div className={`${styles.dropdownItem} ${styles.dropdownItemDisabled}`}>
                  <div className={styles.dropdownItemInfo}>
                    <span className={styles.dropdownItemName}>{error}</span>
                  </div>
                </div>
              )}

              {!isLoading && !error && matches.length === 0 && (
                <div className={`${styles.dropdownItem} ${styles.dropdownItemDisabled}`}>
                  <div className={styles.dropdownItemInfo}>
                    <span className={styles.dropdownItemName}>Ничего не найдено</span>
                    <span className={styles.dropdownItemMeta}>
                      {buildings.length === 0
                        ? 'Нет опубликованных корпусов'
                        : 'Попробуйте изменить запрос'}
                    </span>
                  </div>
                </div>
              )}

              {!isLoading &&
                !error &&
                matches.map((building) => {
                  const ready = building.floors_count >= 1;
                  return (
                    <div
                      key={building.id}
                      className={`${styles.dropdownItem} ${ready ? '' : styles.dropdownItemDisabled}`}
                      onClick={() => {
                        if (ready) openBuilding(building);
                      }}
                    >
                      <div className={styles.dropdownItemInfo}>
                        <span className={styles.dropdownItemName}>{building.name}</span>
                        <span className={styles.dropdownItemMeta}>
                          {ready
                            ? `Код: ${building.code} · ${getPluralFloors(building.floors_count)}`
                            : `Код: ${building.code} · Данные отсутствуют`}
                        </span>
                      </div>
                      {ready && <span className={styles.dropdownItemTag}>Просмотр</span>}
                    </div>
                  );
                })}
            </div>
          )}
        </div>

        <div className={styles.sysStatus}>
          <p>SYS.STATUS // ONLINE</p>
          <p>DB.CONNECTION // ESTABLISHED</p>
        </div>
      </main>
    </div>
  );
};

export default PublicHomePage;
