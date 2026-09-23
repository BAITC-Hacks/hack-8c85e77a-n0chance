DROP INDEX `idx_proposals_task_owner`;--> statement-breakpoint
ALTER TABLE `proposals` ADD `plan` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `proposals` ADD `prototype` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `proposals` ADD `evidence` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `proposals` ADD `progress` text DEFAULT 'none' NOT NULL;--> statement-breakpoint
ALTER TABLE `proposals` ADD `points` integer DEFAULT 0 NOT NULL;--> statement-breakpoint
CREATE INDEX `idx_proposals_task` ON `proposals` (`task`);--> statement-breakpoint
CREATE INDEX `idx_proposals_owner` ON `proposals` (`owner`);--> statement-breakpoint
ALTER TABLE `profiles` ADD `interests` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `profiles` ADD `technologies` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `tasks` ADD `need` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `tasks` ADD `users` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `tasks` ADD `constraints` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `tasks` ADD `contact` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `tasks` ADD `interaction` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `tasks` ADD `confirmed` integer DEFAULT 0 NOT NULL;