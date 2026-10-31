package com.bankpilot.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** Optional local-only migration of existing Day6 users. Credentials come from environment. */
@Component
@ConditionalOnProperty(name="bankpilot.day7.legacy-bootstrap.enabled",havingValue="true")
public class Day7LegacyDemoBootstrap implements ApplicationRunner {
    private final JdbcTemplate jdbc;
    private final String xiaoPassword,xiaoPhone,lisiPassword,lisiPhone;
    public Day7LegacyDemoBootstrap(JdbcTemplate jdbc,
        @Value("${bankpilot.day7.legacy-xiaoming.password:}") String xp,
        @Value("${bankpilot.day7.legacy-xiaoming.phone:}") String xph,
        @Value("${bankpilot.day7.legacy-lisi.password:}") String lp,
        @Value("${bankpilot.day7.legacy-lisi.phone:}") String lph) {
        this.jdbc=jdbc;this.xiaoPassword=xp;this.xiaoPhone=xph;
        this.lisiPassword=lp;this.lisiPhone=lph;
    }
    @Override @Transactional
    public void run(ApplicationArguments args){
        bind(1,"张小明","xiaoming",xiaoPassword,xiaoPhone);
        bind(2,"李四","lisi",lisiPassword,lisiPhone);
    }
    private void bind(long id,String name,String username,String password,String phone){
        Integer exists=jdbc.queryForObject("SELECT COUNT(*) FROM user_credentials WHERE user_id=?",Integer.class,id);
        if(exists!=null && exists>0)return;
        if(password.length()<8 || password.length()>128 || !phone.matches("1[3-9][0-9]{9}"))
            throw new IllegalStateException("Provide unique local demo password and phone for "+username);
        var rows=jdbc.query("SELECT id FROM users WHERE id=? AND display_name=? FOR UPDATE",
            (rs,i)->rs.getLong(1),id,name);
        if(rows.size()!=1)throw new IllegalStateException("Legacy demo user missing: "+username);
        jdbc.update("UPDATE users SET phone=?,phone_verified=0,status='ACTIVE' WHERE id=?",phone,id);
        jdbc.update("INSERT INTO user_credentials(user_id,username,password_hash) VALUES (?,?,?)",
            id,username,new BCryptPasswordEncoder(12).encode(password));
    }
}
