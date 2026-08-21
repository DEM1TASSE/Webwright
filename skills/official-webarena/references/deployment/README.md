# WebArena 环境 @ GCRSANDBOX410

主机名：`GCRSANDBOX410.redmond.corp.microsoft.com`（内网 IP `10.209.224.120`）
访问范围：Microsoft 内网 / VPN。容器绑 0.0.0.0，本机无防火墙，其他 corp 机器直连即可。
这台机器没有公网入站 IP（出站 NAT 167.220.110.x），所以没有做公网暴露。

## 实例 0（基础）

| 站点 | URL |
|---|---|
| Homepage | http://GCRSANDBOX410.redmond.corp.microsoft.com:4399 |
| OneStopShop (Shopping) | http://GCRSANDBOX410.redmond.corp.microsoft.com:7770 |
| CMS (Shopping Admin) | http://GCRSANDBOX410.redmond.corp.microsoft.com:7780/admin （admin / admin1234） |
| Reddit (Postmill) | http://GCRSANDBOX410.redmond.corp.microsoft.com:9999 |
| GitLab | http://GCRSANDBOX410.redmond.corp.microsoft.com:8023 |
| Wikipedia (Kiwix) | http://GCRSANDBOX410.redmond.corp.microsoft.com:8888/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing |
| Map (OpenStreetMap) | http://GCRSANDBOX410.redmond.corp.microsoft.com:3000 |

### Map 的后端服务（前端 JS 直接访问，必须可达）

| 服务 | 端口 | 健康检查 |
|---|---|---|
| 瓦片渲染 | 8080 | `/tile/0/0/0.png` |
| Nominatim 地理编码 | 8085 | `/search?q=...&format=json` |
| OSRM 驾车 / 骑行 / 步行 | 5000 / 5001 / 5002 | `/route/v1/driving/lon,lat;lon,lat` |

## Map 是怎么来的

官方只在 S3 公开桶发布了 map **后端**数据（189GB，桶实际在 us-east-1 而非文档写的 us-east-2），
**前端**（openstreetmap-website，:3000）只存在于 AWS AMI 里。所以前端是从用户的 AMI 实例
`18.223.172.69` 直接搬过来的官方原件（2023-07-21 版），不是从 upstream 重建的——
这点很重要，重建的版本 DOM 会和 map task 的 evaluator 对不上。

搬过来的东西：`openstreetmap-website-web/db` 两个镜像、652MB 源码、142GB Postgres 数据。
map 只有一份，多实例共享（replica.sh 不复制 map）。

## 多实例（并行跑 task）

实例 k 的端口 = 基础端口 + k×100，容器名 `<site>_k`。镜像层共享，每套实例约 8GB 内存、磁盘增量很小。

```bash
/data/webarena/replica.sh up 2       # 起实例 2（约 6 分钟，含 GitLab 启动）
/data/webarena/replica.sh urls 2     # 打印该实例所有 URL
/data/webarena/replica.sh status 2
/data/webarena/replica.sh down 2     # 删除该实例
```

已就绪：实例 0（7770/7780/9999/8023/8888/4399）、实例 1（7870/7880/10099/8123/8988/4499）。

## 所有端点的唯一真相：instances.json

`/data/webarena/instances.json` 列出全部实例和 map 的地址，schema 兼容压测框架原有的
`stress/instances.json`（多了 `map` 和 `tunnel` 两个顶层字段）。

它由 `gen_instances.py` 扫描实际在跑的 `shopping_*` 容器生成，不是手写的静态文件；
`replica.sh up/down` 之后会自动重新生成。手动重建：

```bash
python3.11 /data/webarena/gen_instances.py
```

`env_0.sh` ~ `env_N.sh` 是同样内容的 shell 版本，方便 `source`。

## 在其他机器上跑 task

```bash
export SHOPPING="http://GCRSANDBOX410.redmond.corp.microsoft.com:7770"
export SHOPPING_ADMIN="http://GCRSANDBOX410.redmond.corp.microsoft.com:7780/admin"
export REDDIT="http://GCRSANDBOX410.redmond.corp.microsoft.com:9999"
export GITLAB="http://GCRSANDBOX410.redmond.corp.microsoft.com:8023"
export WIKIPEDIA="http://GCRSANDBOX410.redmond.corp.microsoft.com:8888/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing"
export HOMEPAGE="http://GCRSANDBOX410.redmond.corp.microsoft.com:4399"
python scripts/generate_test_data.py
```

## 管理

```bash
/data/webarena/webarena.sh status      # 容器状态 + HTTP 健康检查
/data/webarena/webarena.sh start|stop
/data/webarena/webarena.sh configure   # 重写 base_url / external_url
/data/webarena/webarena.sh reset       # 跑完 812 条 task 后重置（约 8 分钟）
sudo systemctl restart webarena-homepage@0   # 重启 4399 首页
```

容器已设 `--restart unless-stopped`；homepage 和隧道由 systemd 托管（见下一节），都能扛住重启。

## 持久化（systemd）

隧道和 homepage 都是 systemd 服务，开机自启、进程挂掉自动重拉，不依赖任何 SSH session：

```bash
systemctl status  webarena-tunnel@0      # 反向隧道 -> GCRAZGDL1704 (72.154.168.97)
systemctl status  webarena-homepage@0    # 4399
systemctl status  webarena-homepage@1    # 4499
sudo systemctl restart webarena-tunnel@0
sudo systemctl enable --now webarena-tunnel@1   # 给实例 1 也开隧道（7870/7880/10099/8123/8988/4499）
journalctl -u webarena-tunnel@0 -f       # 看重连日志
```

容器本身是 `--restart unless-stopped`，宿主机重启一并恢复。

## 反向隧道（给 GCRAZGDL1704 用）

GCRAZGDL1704（Azure VM，10.8.162.118）和 410（corpnet 物理机，10.209.224.120）不在同一网络平面，
且只有 410 -> VM 方向可达，所以隧道从 410 这边发起。端口两边同号，VM 上加一行 hosts 即可：

```
127.0.0.1  gcrsandbox410.redmond.corp.microsoft.com GCRSANDBOX410.redmond.corp.microsoft.com
```

加了之后 VM 上用 `env_0.sh` 里那套 FQDN 地址即可，服务端零改动
（Magento/GitLab 会 302 到 FQDN，map 的 JS 也写死了 FQDN 的后端地址，
所以不能直接用 IP 或 localhost 访问）。

端口默认两边同号，**只有 map 前端例外**：GCRAZGDL1704 上 3000 已被一个 python3 进程占用，
所以它在 VM 那边是 **13000**（map 的后端端口 8080/8085/5000-5002 必须同号，JS 里是绝对 URL）。

密钥：`~/.ssh/webarena_tunnel`，公钥已在 VM 的 authorized_keys 里。

## 性能调优（压测后做的）

两处默认配置在这台 128 核机器上表现很差，都已调过并验证：

**GitLab：puma worker 8 → 24**

在 `/etc/gitlab/gitlab.rb` 的 `WEBARENA_TUNING` 块里，`webarena.sh` 和 `replica.sh` 都已内置，
`reset` 和新实例自动带上。改后 `/explore` 在并发 32 下：15.8 → 53.4 RPS，p95 3.99s → 0.82s。

依据：请求耗时分解显示 1.4s 的请求里只有 0.435s 是 CPU，其余在等 Redis（0.486s）和 DB（0.365s）；
同时容器 CPU 不到 1 核、md0 util 0.32%，说明限制来自 worker 槽位而非资源。这种 I/O 等待型负载
加进程直接换并行度。并发 64 时吞吐回落到 37 RPS，拐点在 32-64 之间，还没细定位。

**Map 前端：关掉 Rails 的 development 串行化**

`config/environments/development.rb` 里 `cache_classes` / `eager_load` 都改成 `true`，
`config/puma.rb` 打开 `workers 16` + `preload_app!`。

并发 32 下的三次迭代：4.7 RPS（原始，p95 12.45s）→ 73.5 RPS（4 workers）→ **154.7 RPS**（16 workers，p95 0.26s）。
并发 128 时 292 RPS / p95 0.44s，吞吐还在涨，尚未到拐点。相对原始提升约 62 倍。

worker 从 4 加到 16 的依据：加压采样显示 web 容器吃满约 5 个核（506% CPU）而 db 容器几乎不动
（0.02% CPU、19MB 内存——首页渲染根本不查库），即瓶颈是 Rails 的 CPU 并行度，这台机器有 128 核。
同理，如果要给实例 0/1 各配一个独立 map 前端做隔离，也**不需要复制那 142GB 数据库**：
两个 web 容器可以共用同一个 db 容器和同一组 map 后端，代价只有约 1.5GB 内存。

依据：`cache_classes = false` 会让 Rails 给每个请求套上代码重载 interlock，把请求串行化——
改前吞吐恒定 4.7 RPS，并发从 8 升到 32 完全不变，延迟线性增长，是典型的排队特征。
官方 AMI 也是这么跑的，所以这是对原环境的改进，不是我们部署的缺陷。
原文件备份在同目录的 `.orig`。源码目录是 bind mount，compose 重建不会冲掉这些改动。


## 踩过的坑

1. **GitLab 间歇 500/502**：GitLab 按 CPU 数自动配 puma worker，这台机器 128 核 → 128 个 worker，触发
   `prometheus-client-mmap` 的 `IOError (unmapped file)`。修法是在 `/etc/gitlab/gitlab.rb` 里固定
   `puma['worker_processes'] = 8` 并关掉 `prometheus_monitoring`，然后 `gitlab-ctl reconfigure`。
   `webarena.sh` 和 `replica.sh` 都已内置（用 `WEBARENA_TUNING` 哨兵判断是否已配，
   不能用 `grep worker_processes`——gitlab.rb 里有同名注释行会误判）。
2. **forum / shopping 首次启动慢**：镜像里的 Postgres/MySQL 要做崩溃恢复，forum 花了约 6 分钟才从 500 转 200，属正常。
3. **Map 部署的三个坑**：
   - 官方 cloud-init 的 `--strip-components` 值和实际 tar 对不上：tile 该剥 4 层（脚本写 5）、
     `osm_dump` 该剥 1 层（脚本写 0）。照抄会解压到错路径，容器起来是空的。
   - nominatim 数据卷解压后属主是源机器的 uid 991，而镜像里 postgres 是 101:103，
     容器报 `cluster is owned by user id 991 which does not exist`，需要 chown。
   - AMI 的 `pg_hba.conf` 顶部有人手工加了 `host all openstreetmap 0.0.0.0/0 reject`
     （堵对外暴露的 54321）。AMI 上没暴雷是因为它的 Rails 连接池建立在改规则之前。
     我们这边要在 reject 之前插入允许 docker 网段的规则，并且不发布 54321。
4. **从 EC2 拉数据**：那台 AMI 是积分耗尽的 t2.2xlarge（CPU steal 46%），
   zstd 压缩比不压缩还慢 9 倍。改成不压缩 + 6 路分片，1MB/s → 65MB/s。
5. **下载**：metis 镜像站单连接约 17MB/s，12 连接分块可到 100MB/s+。
   `dl.sh` 用的是"分块下载 + cat 合并"，合并要多读写一整个文件（88GB 的 zim 多花了 176GB I/O），
   下次可以改成各分块 `dd seek=` 直接写进同一个预分配文件。

## 文件位置

- 镜像 tar / wiki zim：`/data/webarena/tars/`（共 279GB，可在确认环境稳定后删除以释放空间）
- 脚本：`dl.sh`（下载）、`setup.sh`（首次编排）、`webarena.sh`（管理）、`replica.sh`（多实例）
- 日志：`dl.log`、`setup.log`、`load_*.log`、`gitlab*_reconf*.log`、`replica1.log`
- 官方 repo：`/data/webarena/repo/`

---

## 这份目录的来源与状态

原件在产出 812 结果的那台机器的 `/data/webarena/`，不在任何 git 里，随机器一起会丢。
这里是一份快照，脚本内容未改，只把 README 里的机器专属结果路径替换成了 `<results-root>`。

脚本里出现的 `magentouser/MyPassword`、`admin/admin1234`、`byteblaze/hello1234`
是 WebArena 官方公开的默认凭据（官方仓库与 benchmark 自带的 `password.html` 里就有），
不是密钥。真正的密钥（模型网关的 API key）从不在这些脚本里，由调用方从环境注入。

`env_INSTANCE.sh.example` 是实例 k 的环境变量模板；实例 k 的端口一律是基准端口 + 100k
（map 除外，全实例共享一份）。`deployment.example.json` 是 harness 侧的部署描述模板。

### 里面已经焊进去的修复，换机器时不要退回

- `replica.sh up` 设 `web/url/redirect_to_base = 0`。不设的话 Magento 在任何 host
  与存储的 base_url 不字面相等时 302 死循环，而 Chromium 会把 host 小写，必现。
- GitLab 容器 `--shm-size=2g`。默认 64M 会被 Prometheus 的 mmap 指标写满，
  之后每个请求都 500（`IOError: unmapped file`），而 `docker ps` 与 `gitlab-ctl status` 都显示健康。
- GitLab `puma["worker_processes"] = 24`。128 核机器上 GitLab 会按核数起 128 个 worker，
  同样触发 prometheus-client-mmap 的 unmapped file。
- `postgresql["max_connections"] = 600`。
- `down` 的 pkill 模式是 `flask.*--port=`，不是 `flask run --host=`——
  实际命令行里 `--app app` 夹在中间，旧模式匹配不上，端口不释放，下次 `up` 直接拒启。
- 官方 cloud-init 的 tar `--strip-components` 值对不上我们拿到的 tarball，
  tile 数据浅一层、osm_dump 深一层，`map_backend.sh` 里是修正后的值。

### 换机器后必须重新确认的

- `HOST` 与 `IP`（`gen_instances.py` 顶部硬编码）
- 反向隧道的目标机与端口（`tunnel.sh`）
- `/data/webarena/tars`（283G）与 `map`（198G）不在这里，需从官方 S3 重新下载，
  `dl.sh` / `dl_mapdb.sh` / `dl_map.py` 是当时用的下载脚本。map 前端来自官方 AMI，
  不能用 upstream 的 openstreetmap-website 重建——重建版的 DOM 与 evaluator 对不上。
