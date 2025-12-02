CREATE DATABASE  IF NOT EXISTS `cal_db` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;
USE `cal_db`;
-- MySQL dump 10.13  Distrib 8.0.44, for Win64 (x86_64)
--
-- Host: localhost    Database: cal_db
-- ------------------------------------------------------
-- Server version	8.0.44

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `available_slots`
--

DROP TABLE IF EXISTS `available_slots`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `available_slots` (
  `slot_id` int NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL,
  `user_id` int NOT NULL,
  `start_time` datetime NOT NULL,
  `end_time` datetime NOT NULL,
  PRIMARY KEY (`slot_id`),
  KEY `group_id` (`group_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `available_slots_ibfk_1` FOREIGN KEY (`group_id`) REFERENCES `cal_groups` (`group_id`) ON DELETE CASCADE,
  CONSTRAINT `available_slots_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `available_slots`
--

LOCK TABLES `available_slots` WRITE;
/*!40000 ALTER TABLE `available_slots` DISABLE KEYS */;
INSERT INTO `available_slots` VALUES (1,2,2,'2025-11-27 11:00:00','2025-11-27 16:00:00'),(2,4,2,'2025-11-07 11:50:00','2025-11-07 00:50:00'),(3,4,3,'2025-11-27 13:53:00','2025-11-27 18:55:00'),(4,4,2,'2025-12-02 10:00:00','2025-12-02 14:00:00'),(5,4,3,'2025-12-17 05:30:00','2025-12-17 10:30:00'),(6,4,3,'2025-12-02 09:00:00','2025-12-02 11:00:00'),(7,4,2,'2025-12-10 03:00:00','2025-12-10 14:00:00'),(8,4,3,'2025-12-09 07:30:00','2025-12-09 10:30:00'),(9,4,4,'2025-12-24 10:00:00','2025-12-24 20:00:00'),(11,4,2,'2025-12-25 00:00:00','2025-12-26 00:00:00'),(13,4,2,'2025-12-24 00:00:00','2025-12-24 11:00:00'),(14,4,3,'2025-12-24 00:00:00','2025-12-24 16:00:00');
/*!40000 ALTER TABLE `available_slots` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `cal_groups`
--

DROP TABLE IF EXISTS `cal_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cal_groups` (
  `group_id` int NOT NULL AUTO_INCREMENT,
  `group_name` varchar(100) NOT NULL,
  `invite_code` varchar(50) NOT NULL,
  `created_by` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`group_id`),
  UNIQUE KEY `invite_code` (`invite_code`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cal_groups`
--

LOCK TABLES `cal_groups` WRITE;
/*!40000 ALTER TABLE `cal_groups` DISABLE KEYS */;
INSERT INTO `cal_groups` VALUES (1,'hyunho0728의 공유 캘린더','3a9c25a7',2,'2025-11-25 01:45:37'),(2,'hyunho0728의 공유 캘린더','527438a0',2,'2025-11-25 01:48:04'),(3,'domino의 공유 캘린더','a4daa154',3,'2025-11-25 01:49:09'),(4,'hyunho0728의 공유 캘린더','1948e57f',2,'2025-11-25 01:49:15'),(5,'hyunho0728의 공유 캘린더','7b13d190',2,'2025-11-25 01:51:48'),(6,'선혜의 공유 캘린더','8915cd68',4,'2025-12-02 04:15:58');
/*!40000 ALTER TABLE `cal_groups` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `group_members`
--

DROP TABLE IF EXISTS `group_members`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `group_members` (
  `group_id` int NOT NULL,
  `user_id` int NOT NULL,
  `joined_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`group_id`,`user_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `group_members_ibfk_1` FOREIGN KEY (`group_id`) REFERENCES `cal_groups` (`group_id`) ON DELETE CASCADE,
  CONSTRAINT `group_members_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `group_members`
--

LOCK TABLES `group_members` WRITE;
/*!40000 ALTER TABLE `group_members` DISABLE KEYS */;
INSERT INTO `group_members` VALUES (1,2,'2025-11-25 01:45:37'),(2,2,'2025-11-25 01:48:04'),(3,3,'2025-11-25 01:49:09'),(4,2,'2025-11-25 01:49:15'),(4,3,'2025-11-25 01:49:54'),(4,4,'2025-12-02 04:34:20'),(5,2,'2025-11-25 01:51:48'),(6,4,'2025-12-02 04:15:58');
/*!40000 ALTER TABLE `group_members` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `schedules`
--

DROP TABLE IF EXISTS `schedules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `schedules` (
  `schedule_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `title` varchar(150) NOT NULL,
  `description` text,
  `start_date` datetime NOT NULL,
  `end_date` datetime NOT NULL,
  `color` varchar(7) DEFAULT '#3788d8',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`schedule_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `schedules_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `schedules`
--

LOCK TABLES `schedules` WRITE;
/*!40000 ALTER TABLE `schedules` DISABLE KEYS */;
INSERT INTO `schedules` VALUES (1,1,'test',NULL,'2025-11-26 00:00:00','2025-11-26 01:00:00','#3788d8','2025-11-25 00:59:59'),(2,2,'123',NULL,'2025-11-26 00:00:00','2025-11-26 01:00:00','#3788d8','2025-11-25 01:10:44'),(3,3,'밥',NULL,'2025-11-10 01:06:00','2025-11-10 02:06:00','#3788d8','2025-11-25 01:24:00'),(4,2,'하천에서 달리기',NULL,'2025-11-25 20:13:00','2025-11-25 21:13:00','#3788d8','2025-11-25 01:31:04'),(5,4,'저녁약속',NULL,'2025-12-01 19:00:00','2025-12-01 20:00:00','#3788d8','2025-12-02 04:13:53'),(6,4,'영화 데이트',NULL,'2025-12-07 14:00:00','2025-12-07 15:00:00','#3788d8','2025-12-02 04:14:26'),(7,4,'바다여행~!',NULL,'2025-12-24 10:00:00','2025-12-24 11:00:00','#3788d8','2025-12-02 04:14:45'),(8,2,'실내 사이클',NULL,'2025-12-03 20:00:00','2025-12-03 21:00:00','#3788d8','2025-12-02 05:05:09');
/*!40000 ALTER TABLE `schedules` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `user_id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `email` varchar(100) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'admin','admin@example.com','dummyhash','2025-11-25 00:59:11'),(2,'hyunho0728','yu16891@gmail.com','scrypt:32768:8:1$m3icoxZrrAnifk2s$cd9358b61b9b8b16942579be147836533131141d225603cff08f47191670581f02b1dfc9bf465f7c89f029f3e205c914ca27248b84ae425a2b44113d445842c3','2025-11-25 01:10:24'),(3,'domino','kkunis.repeat@gmail.com','scrypt:32768:8:1$lnYODZ34qAMwnHuW$98e443028f394a1530e19399759bd62c490c4b9feb2e7a4a98151b73bc49c5e740bde1be5045757c45c8d4846838ac53a1b12dd699d1fb4998ae7e8b9bba03dd','2025-11-25 01:14:24'),(4,'선혜','0624ssh@naver.com','scrypt:32768:8:1$ZbePlVZxi9cJl6al$9a3d4fc47feb618c3642febadf8b55273443d72660c57bac072b8ad917d7a692d533e8cb5e37e6b1dce8f5a5b38083560174bf8f0927e8eed30dfcfbdc46ced3','2025-12-02 04:12:30'),(5,'hhhhhhhhh','hhhh@123','scrypt:32768:8:1$nAmoYdsk6tqeWNSa$0eadf85b65bfe0269a761b5ec042a12f16022b3764ad2d4de926c838a29980dbf1887a8285fde34ea6c223bb1b88924b837e87262860f6b1094e485787bb21d5','2025-12-02 06:03:34');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-12-02 15:14:33
